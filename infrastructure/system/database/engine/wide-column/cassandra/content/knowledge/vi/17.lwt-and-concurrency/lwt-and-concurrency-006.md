# Trường `[applied]` cùng giá trị hiện tại khi điều kiện thất bại

> **Chương:** LWT và đồng thời  
> **Phạm vi:** Apache Cassandra, CQL và ứng dụng Java sử dụng Cassandra Java Driver 4.x.

## 1. Tại sao cần đọc cả `[applied]` lẫn giá trị hiện tại?

Cassandra là cơ sở dữ liệu phân tán theo mô hình *wide-column*. Dữ liệu được phân phối theo **partition key** và được nhân bản trên các nút. Với `INSERT` hoặc `UPDATE` thông thường, Cassandra không mặc định kiểm tra xem bản ghi đã tồn tại hay dữ liệu còn khớp với trạng thái mà ứng dụng vừa đọc hay không. Khi có nhiều tác nhân cùng thay đổi một dòng, một tác nhân có thể ghi đè quyết định của tác nhân khác.

**Lightweight Transaction (LWT)** cung cấp phép ghi có điều kiện theo cơ chế *compare-and-set* (CAS) và sử dụng Paxos để phối hợp các bản sao. Các dạng điển hình là:

- `INSERT ... IF NOT EXISTS`: chỉ tạo dòng nếu dòng chưa tồn tại.
- `UPDATE ... IF <điều kiện>`: chỉ cập nhật khi các cột thỏa điều kiện.
- `UPDATE ... IF EXISTS` hoặc `DELETE ... IF EXISTS`: chỉ thao tác khi dòng tồn tại.

Kết quả của thao tác LWT thành công ở tầng giao tiếp là **một dòng kết quả** có cột đặc biệt tên `[applied]`:

| Giá trị `[applied]` | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `true` | Điều kiện CAS đã thỏa và thao tác được chấp nhận áp dụng. | Xác nhận thành công cho yêu cầu tương ứng. |
| `false` | Điều kiện CAS không thỏa; **thay đổi được yêu cầu đã không được áp dụng**. | Đọc thông tin xung đột trả về; quyết định báo lỗi nghiệp vụ, đọc lại hoặc thử lại có kiểm soát. |
| Không nhận được kết quả vì timeout/mất kết nối | Chưa biết chắc thao tác đã được áp dụng hay chưa. | Đối soát trạng thái, cân nhắc tính idempotent; tuyệt đối không suy diễn thành `false`. |

`[applied]` là **cột trong kết quả của lệnh điều kiện**, không phải cột lưu sẵn trong schema. `[applied]=true` nói rằng điều kiện thành công; nó không khẳng định giá trị mới khác giá trị cũ. Ngược lại, `[applied]=false` là một **xung đột điều kiện bình thường**, không phải lỗi cú pháp hay lỗi kết nối.

## 2. Khi thất bại, Cassandra trả về những giá trị nào?

Điểm dễ bỏ sót là dòng kết quả có thể chứa thêm **giá trị đang tồn tại ở thời điểm kiểm tra CAS**. Số cột được trả về phụ thuộc vào cách viết điều kiện:

| Lệnh CQL | Khi `[applied]=true` | Khi `[applied]=false` |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Thường chỉ có `[applied]`. | Có `[applied]` và **các cột của dòng đã tồn tại** tại khóa chính đó, kể cả các giá trị `null`. |
| `UPDATE ... IF col_a = ... AND col_b = ...` | Thường chỉ có `[applied]`. | Có `[applied]` và **giá trị hiện tại của các cột được nêu trong mệnh đề `IF`** (`col_a`, `col_b`). |
| `UPDATE ... IF EXISTS` | Chỉ có `[applied]`. | Chỉ có `[applied]`; không kèm nội dung dòng. |
| `DELETE ... IF ...` | Kết quả điều kiện theo `IF` tương ứng. | Chỉ dựa vào các cột mà chính loại điều kiện đó trả về; không mặc định có toàn bộ dòng. |

Vì vậy, **không được viết ứng dụng với giả định tất cả LWT thất bại đều trả về toàn bộ bản ghi**. Một lệnh `UPDATE ... IF version = ?` giúp lấy phiên bản hiện tại khi xung đột, nhưng không tự động trả về `quantity`, `status` hay các trường khác nếu chúng không nằm trong `IF`. Một câu `SELECT` bổ sung có thể cần thiết để tái tính toán nghiệp vụ.

### Đọc đúng giá trị `null` và cột vắng mặt

Hai trường hợp rất khác nhau:

- **Cột có trong kết quả nhưng giá trị là `null`**: kết quả cung cấp cột đó, song chưa có giá trị hiện hữu (hoặc giá trị không còn sống). Ví dụ dòng tồn tại mà `note` chưa từng được ghi.
- **Cột hoàn toàn không có trong metadata kết quả**: kiểu LWT này không trả về cột đó. Không thể kết luận cột trong database bằng `null` chỉ vì kết quả không chứa nó.

Trước khi đọc các trường tùy chọn, ứng dụng cần biết schema của kết quả từ chính câu lệnh đã gửi; có thể kiểm tra danh sách cột trong `Row.getColumnDefinitions()` khi xử lý nhiều loại lệnh.

## 3. Thực hành CQL: tạo dòng, cập nhật và phát hiện xung đột

Giả sử bạn đang dùng một **keyspace thử nghiệm** và bảng quản lý tồn kho được truy vấn trực tiếp theo `sku`, là partition key. Các ví dụ dưới đây giả định khóa `'BOOK-42'` chưa tồn tại trước bước đầu tiên.

```cql
CREATE TABLE IF NOT EXISTS stock_guard (
    sku text PRIMARY KEY,
    quantity int,
    version int,
    updated_by text
);
```

### Bước A — Tạo dòng bằng `IF NOT EXISTS`

```cql
INSERT INTO stock_guard (sku, quantity, version, updated_by)
VALUES ('BOOK-42', 10, 1, 'seed')
IF NOT EXISTS;
```

Khi dòng chưa tồn tại, kết quả minh họa trong `cqlsh` là:

```text
 [applied]
-----------
      True
```

Gửi một lệnh tạo cùng khóa chính nhưng với nội dung khác:

```cql
INSERT INTO stock_guard (sku, quantity, version, updated_by)
VALUES ('BOOK-42', 99, 1, 'worker-B')
IF NOT EXISTS;
```

Kết quả kỳ vọng, trình bày rút gọn:

```text
 [applied] | sku     | quantity | version | updated_by
-----------+---------+----------+---------+-----------
     False | BOOK-42 |       10 |       1 | seed
```

Lệnh thứ hai bị từ chối; **`quantity` vẫn là 10**, không trở thành 99. Các cột sau `[applied]` là dữ liệu của dòng **đã có**, không phải các giá trị `99` và `worker-B` mà tác nhân mới định ghi. Đó là thông tin hữu ích để phát hiện xung đột khi đăng ký tên duy nhất, tạo tài nguyên theo khóa hoặc chặn tạo trùng.

### Bước B — Ghi theo phiên bản đã quan sát

Một tác nhân đã đọc `quantity=10` và `version=1`, sau đó quyết định giảm số lượng xuống 7. Nó thực hiện:

```cql
UPDATE stock_guard
SET quantity = 7,
    version = 2,
    updated_by = 'worker-A'
WHERE sku = 'BOOK-42'
IF quantity = 10 AND version = 1;
```

Kết quả:

```text
 [applied]
-----------
      True
```

Cả hai điều kiện đều đúng tại thời điểm CAS, nên cập nhật thành công. Một tác nhân khác, vẫn tin rằng tồn kho bằng 10 và phiên bản bằng 1, thực hiện sau đó:

```cql
UPDATE stock_guard
SET quantity = 9,
    version = 2,
    updated_by = 'worker-B'
WHERE sku = 'BOOK-42'
IF quantity = 10 AND version = 1;
```

Kết quả thất bại có dạng (thứ tự cột trình bày có thể khác):

```text
 [applied] | quantity | version
-----------+----------+--------
     False |        7 |       2
```

Giá trị `7` và `2` cho biết trạng thái khiến điều kiện của tác nhân B không thỏa. **`updated_by` không bắt buộc được trả về**, bởi cột này không xuất hiện trong `IF`. Dữ liệu thực tế vẫn thuộc lần cập nhật của A.

Đây là điểm cốt lõi: khách hàng có thể nhận ngay **giá trị đối chiếu đang lưu** mà không phải đoán vì sao CAS thất bại. Nhưng các giá trị đó chỉ phản ánh thời điểm điều kiện được đánh giá; một tác nhân C có thể tiếp tục cập nhật dữ liệu trước khi B quyết định bước kế tiếp.

### Bước C — `IF EXISTS` không cho biết nội dung dòng

```cql
UPDATE stock_guard
SET updated_by = 'worker-C'
WHERE sku = 'NOT-FOUND'
IF EXISTS;
```

```text
 [applied]
-----------
     False
```

Lệnh thất bại vì dòng không tồn tại. Kết quả không kèm `quantity`, `version` hay `updated_by`; ứng dụng không được cố lấy các trường ấy từ `Row`. Nếu thực sự cần biết trạng thái dữ liệu cho quyết định tiếp theo, hãy phát truy vấn thích hợp.

## 4. Đọc xung đột trong một cuộc đua ghi

Giả sử hai dịch vụ A và B đã cùng đọc trạng thái `(quantity=10, version=1)`.

| Thứ tự | Tác nhân | Thao tác | Phản hồi |
| --- | --- | --- | --- |
| 1 | A | CAS từ `(10, 1)` sang `(7, 2)`. | `[applied]=true`. |
| 2 | B | CAS từ `(10, 1)` sang `(9, 2)`. | `[applied]=false`; `quantity=7`, `version=2`. |
| 3 | B | Kiểm tra lại yêu cầu giảm tồn kho theo trạng thái vừa biết. | Có thể yêu cầu CAS mới với phiên bản 2, nếu còn đủ hàng và nghiệp vụ cho phép. |

Nếu B vẫn cần giảm số lượng thêm 1, nó phải tính lại theo trạng thái `7` để đề xuất `6` với điều kiện `IF quantity=7 AND version=2`. Nếu một tác nhân khác đã thay đổi dữ liệu thành phiên bản 3 trước khi B gửi lệnh, CAS tiếp theo lại trả `false`; đó là cách cơ chế bảo vệ tránh cập nhật dựa trên dữ liệu cũ.

**Đừng biến vòng lặp CAS thành retry vô hạn.** Một cách xử lý hợp lý là giới hạn số lần thử, có backoff khi tranh chấp cao, tính lại quy tắc nghiệp vụ mỗi vòng và trả trạng thái xung đột rõ ràng khi hết lượt.

## 5. Đọc `[applied]` và cột hiện tại trong Java Driver 4.x

Cassandra Java Driver 4.x cung cấp `ResultSet.wasApplied()` để đọc kết quả CAS. Phương thức này **không tiêu thụ dòng kết quả**; có thể gọi `result.one()` sau đó để lấy các cột khi xung đột.

Ví dụ sau giả định một `CqlSession` đã được cấu hình để kết nối đến keyspace chứa `stock_guard`. Giá trị `expectedQuantity` và `expectedVersion` phải đến từ trạng thái đã đọc hoặc từ vòng CAS trước; ví dụ truyền `(10, 1)` tương ứng bước B.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class StockCasExample {
    public static void tryUpdate(
            CqlSession session,
            String sku,
            int expectedQuantity,
            int expectedVersion,
            int newQuantity) {

        PreparedStatement prepared = session.prepare(
            "UPDATE stock_guard " +
            "SET quantity = ?, version = ?, updated_by = ? " +
            "WHERE sku = ? IF quantity = ? AND version = ?"
        );

        BoundStatement statement = prepared.bind(
                newQuantity,
                expectedVersion + 1,
                "java-service",
                sku,
                expectedQuantity,
                expectedVersion)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        ResultSet result = session.execute(statement);

        if (result.wasApplied()) {
            System.out.println("CAS thành công");
            return;
        }

        // Vì IF kiểm tra quantity và version, hai cột này
        // có trong dòng kết quả khi điều kiện không thỏa.
        Row current = result.one();
        if (current == null) {
            throw new IllegalStateException("Thiếu dòng kết quả của LWT");
        }

        Integer actualQuantity = current.isNull("quantity")
                ? null : current.getInt("quantity");
        Integer actualVersion = current.isNull("version")
                ? null : current.getInt("version");

        System.out.printf(
            "Xung đột CAS: quantity=%s, version=%s%n",
            actualQuantity, actualVersion
        );

        // Tại đây: xác thực lại quy tắc nghiệp vụ rồi mới
        // quyết định báo xung đột, SELECT thêm hoặc thử CAS mới.
    }
}
```

**Giải thích những chỗ dễ sai trong code:**

1. `wasApplied()` chỉ phản ánh trạng thái điều kiện khi lệnh là LWT. Với câu lệnh thường, API có thể trả `true` theo quy ước; không dùng nó để suy luận một lệnh ghi thường đã tạo hay sửa dòng.
2. `result.one()` trả về dòng kết quả của LWT. Phải kiểm tra `[applied]` trước vì khi thành công, các cột `quantity` và `version` không phải là một phần của kết quả.
3. `isNull(...)` kiểm tra giá trị `null` của cột **được đảm bảo tồn tại trong kết quả này**. Nếu viết một bộ xử lý chung cho `IF NOT EXISTS`, `IF EXISTS` và `IF col=...`, hãy kiểm tra metadata cột trước khi đọc.
4. `LOCAL_QUORUM` là mức nhất quán ghi thông thường, còn `LOCAL_SERIAL` điều khiển pha điều kiện LWT trong một datacenter. Chọn `SERIAL` hay `LOCAL_SERIAL` và mức ghi phù hợp với topology cùng yêu cầu nhất quán của hệ thống; đây là các cấu hình khác nhau.

Nếu dùng API hàng thấp, tên trường trả về là **`[applied]` (có ngoặc vuông)**; dùng `wasApplied()` giúp tránh nhầm với tên `applied`.

## 6. Những quyết định sau khi nhận `[applied]=false`

Tùy nghiệp vụ, thất bại của CAS không nhất thiết nên được thử lại:

- **Tạo bản ghi duy nhất:** `INSERT ... IF NOT EXISTS` thất bại có thể được chuyển thành `409 Conflict`, đồng thời dùng khóa hoặc thông tin của dòng hiện hữu để giải thích xung đột. Không tự sửa dữ liệu cũ chỉ vì yêu cầu mới khác nó.
- **Optimistic locking:** `UPDATE ... IF version=?` thất bại nghĩa là phiên bản mong đợi không còn đúng. Trả về phiên bản thực tế, truy vấn lại khi cần nhiều trường hơn, rồi yêu cầu người dùng giải quyết khác biệt hoặc áp dụng phép tính lại.
- **Trừ số lượng hay chuyển trạng thái:** xem lại mọi bất biến, chẳng hạn tồn kho không âm hoặc thứ tự chuyển trạng thái hợp lệ; chỉ CAS lại nếu trạng thái hiện tại cho phép.
- **`IF EXISTS` thất bại:** hiểu rằng dòng không tồn tại đối với điều kiện đã xét; kết quả không tự chứa dữ liệu thay thế.

Cũng cần phân biệt ba thao tác trong ứng dụng:

| Tình huống | Có được xem là ghi thành công? | Có nên retry ngay lệnh y hệt? |
| --- | --- | --- |
| Nhận `[applied]=true` | Có, cho CAS vừa thực hiện. | Không cần. |
| Nhận `[applied]=false` | Không; điều kiện không thỏa. | Không mù quáng; phải đánh giá trạng thái và nghiệp vụ. |
| Nhận timeout/lỗi giao tiếp trước khi có kết quả | **Chưa xác định.** | Đối soát trước, đặc biệt với thao tác có tác động nghiệp vụ hoặc không idempotent. |

Bởi LWT dựa trên Paxos, mỗi thao tác điều kiện cần thêm các vòng trao đổi giữa replica và thường có độ trễ/chi phí cao hơn ghi bình thường. Dùng LWT tại những chỗ thực sự cần điều kiện cạnh tranh; thiết kế truy vấn theo partition key để giới hạn phạm vi phối hợp. LWT không phải giao dịch đa bảng/đa phân vùng kiểu RDBMS.

## 7. Các lỗi hiểu sai thường gặp

**“`false` nghĩa là lỗi Cassandra.”** Sai. Đó là kết quả xác định rằng điều kiện đã không thỏa, và lệnh cập nhật bị từ chối.

**“Khi `false`, mọi cột trả về đều là giá trị tôi muốn ghi.”** Sai. Với `INSERT IF NOT EXISTS` chúng là dữ liệu của dòng đã có; với `UPDATE ... IF` đó là giá trị hiện hành của các cột được đem so sánh.

**“Khi `false`, luôn có nguyên dòng để dùng lại.”** Sai. `UPDATE ... IF version=?` chủ yếu trả lại `version`; `UPDATE ... IF EXISTS` thường chỉ trả `[applied]`.

**“Giá trị trả về là dữ liệu mới nhất cho đến khi tôi ghi lần tiếp theo.”** Sai. Nó phản ánh trạng thái được thấy khi CAS kiểm tra. Các tác nhân khác có thể đã tạo phiên bản tiếp theo ngay sau đó.

**“Timeout giống `[applied]=false`.”** Sai. Timeout hoặc mất kết nối khiến kết quả CAS chưa xác định; cần đối soát hoặc chiến lược retry an toàn.

## 8. Tự thực hành để kiểm chứng

Trên một bảng thử nghiệm riêng, làm lần lượt:

1. Tạo `stock_guard` và chèn một SKU mới bằng `IF NOT EXISTS` hai lần. So sánh số cột trả về giữa lần thành công và lần bị từ chối.
2. Chạy một `UPDATE` với `IF quantity = ... AND version = ...` đúng; chạy lại điều kiện cũ sau khi phiên bản đã tăng. Xác định các cột hiện tại trả về trong lần thất bại.
3. Thử một lệnh `UPDATE ... IF EXISTS` cho SKU không có thật; đối chiếu để thấy kết quả không kèm dữ liệu hàng.
4. Trong Java, hiển thị `wasApplied()` rồi đọc `Row` khi xung đột. Thử thêm một `SELECT` để đối chiếu, đồng thời ghi nhớ rằng `SELECT` có thể nhìn thấy trạng thái mới hơn do hoạt động đồng thời.

**Ghi nhớ:** kiểm tra `[applied]` trước, đọc **đúng các cột mà dạng điều kiện trả về** khi thất bại, và xem thông tin đó là cơ sở để đưa ra một quyết định cạnh tranh mới, không phải quyền được ghi đè trạng thái hiện tại.

## Tham khảo

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html): cú pháp `INSERT IF NOT EXISTS`, `UPDATE IF` và chi phí của điều kiện.
- [DataStax — Lightweight Transactions, specialized results](https://docs.datastax.com/en/drivers/python/3.1/lwt.html): hình dạng `[applied]` và các cột trả về cho từng kiểu điều kiện.
- [Apache Cassandra Java Driver 4.19 — ResultSet](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): hợp đồng của `wasApplied()`.
