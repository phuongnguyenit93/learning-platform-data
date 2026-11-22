# ONE, TWO, THREE, QUORUM và ALL trong Apache Cassandra

Trong Apache Cassandra, các mức nhất quán **`ONE`, `TWO`, `THREE`, `QUORUM` và `ALL`** trả lời một câu hỏi rất thực tế: **coordinator phải đợi bao nhiêu replica phản hồi thành công trước khi báo kết quả của một lần đọc hoặc ghi cho ứng dụng?** Đây là lựa chọn của từng thao tác, có ảnh hưởng trực tiếp đến độ trễ, khả năng chịu lỗi và khả năng quan sát dữ liệu vừa ghi.

Bài học thuộc chương **Nhất quán đọc/ghi** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Mục tiêu chung của mô-đun là hiểu kiến trúc phân tán và mô hình wide-column của Cassandra, thiết kế bảng theo truy vấn và partition key, đồng thời thực hành CQL, replication, compaction, repair, xử lý lỗi và kết nối Java. Trong phạm vi bài này, chúng ta tập trung vào **năm mức nhất quán dựa trên số lượng replica**, cách tính toán và ý nghĩa vận hành của chúng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **replication factor (RF)** với **consistency level (CL)**.
2. Tính số phản hồi bắt buộc của `ONE`, `TWO`, `THREE`, `QUORUM` và `ALL` khi RF thay đổi.
3. Xác định mức nhất quán nào vẫn có thể thành công khi một hoặc nhiều replica không phản hồi.
4. Lý giải vì sao lựa chọn CL đọc và CL ghi phải xem xét **cùng nhau**.
5. Áp dụng CL cho từng câu lệnh bằng `cqlsh` và Apache Cassandra Java Driver.
6. Tránh các suy luận sai về quorum, datacenter, dữ liệu cũ và timeout.

## 2. Bản chất của một mức nhất quán

### Replica, coordinator và RF

Một **partition** được chọn thông qua **partition key**. Cassandra sử dụng thông tin phân bố dữ liệu và chiến lược replication của keyspace để xác định những node nào là **replica** của partition đó.

- **Replica**: node lưu bản sao của partition.
- **Replication factor (RF)**: số replica được cấu hình cho một partition, thường được xác định riêng cho từng datacenter qua `NetworkTopologyStrategy`.
- **Coordinator**: node nhận yêu cầu từ client và điều phối các replica cần tham gia.
- **Consistency level (CL)**: ngưỡng phản hồi coordinator phải nhận cho **lần đọc hoặc ghi cụ thể** trước khi trả về thành công.

Ví dụ trong **một datacenter, RF = 3**, partition của người dùng `U1` có ba replica:

```text
Client
   |
   v
Coordinator
   |------> Replica A
   |------> Replica B
   |------> Replica C

RF = 3: ba bản sao dữ liệu của partition U1
CL = TWO: cần 2 phản hồi hợp lệ để báo thành công
```

Điểm mấu chốt: **CL không quyết định số bản sao được tạo**. Với `CL=TWO`, Cassandra vẫn tìm cách đưa mutation tới các replica đích; nó chỉ **không bắt client đợi ACK của toàn bộ ba replica**. Tương tự, coordinator của một truy vấn đọc có thể liên hệ nhiều replica, sử dụng dữ liệu và digest để đối chiếu kết quả; **số lời gọi thực tế có thể nhiều hơn ngưỡng CL**.

### Phản hồi hợp lệ khi đọc và khi ghi

**Khi ghi**, ACK thường biểu thị replica đã xử lý và chấp nhận mutation theo đường ghi của Cassandra. Chỉ khi đủ số ACK theo CL, coordinator mới trả về thành công. ACK không có nghĩa tất cả replica khác đã cập nhật xong.

**Khi đọc**, coordinator phải thu thập đủ phản hồi của các replica theo CL, rồi xác định dữ liệu cần trả về. Việc so sánh dữ liệu/digest giữa replica và hòa giải phiên bản khác nhau có thể khiến đọc `TWO`, `THREE` hoặc `QUORUM` phát hiện dữ liệu không đồng nhất tốt hơn đọc `ONE`.

Các mức CL trong bài này có thể dùng cho **đọc và ghi thông thường**. Những mức `ANY` (ghi), `LOCAL_ONE`, `LOCAL_QUORUM`, `EACH_QUORUM` và `SERIAL`/`LOCAL_SERIAL` phục vụ các nhu cầu khác và sẽ được nhắc tới để tránh nhầm lẫn.

## 3. Năm mức nhất quán: định nghĩa và công thức

Giả sử một partition có **N replica** trong phạm vi được xét. Đối với `ONE`, `TWO`, `THREE`, ngưỡng phản hồi là **số tuyệt đối**; với `QUORUM`, ngưỡng phụ thuộc RF; còn `ALL` cần tất cả replica.

| Consistency level | Số phản hồi tối thiểu | Ý nghĩa |
| --- | ---: | --- |
| `ONE` | **1** | Chỉ cần một replica phản hồi. |
| `TWO` | **2** | Cần hai replica khác nhau phản hồi. |
| `THREE` | **3** | Cần ba replica khác nhau phản hồi. |
| `QUORUM` | **⌊N/2⌋ + 1** | Cần **đa số tuyệt đối** replica. |
| `ALL` | **N** | Phải nhận phản hồi của **tất cả replica** của partition. |

Với một datacenter, `N` chính là RF của datacenter đó. `QUORUM` tính bằng:

\[
Q = \left\lfloor \frac{RF}{2} \right\rfloor + 1
\]

Ví dụ:

| RF | `ONE` | `TWO` | `THREE` | `QUORUM` | `ALL` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | Không đủ replica | Không đủ replica | **1** | **1** |
| 2 | 1 | 2 | Không đủ replica | **2** | **2** |
| 3 | 1 | 2 | 3 | **2** | **3** |
| 4 | 1 | 2 | 3 | **3** | **4** |
| 5 | 1 | 2 | 3 | **3** | **5** |

**Nhận xét quan trọng:**

- Với **RF = 3**, `TWO` và `QUORUM` cùng cần **2** phản hồi; `THREE` và `ALL` cùng cần **3**.
- Với **RF = 5**, `THREE` và `QUORUM` cùng cần **3**, nhưng `TWO` chỉ cần **2**.
- `TWO` và `THREE` giữ nguyên ngưỡng **2** hoặc **3**, ngay cả khi RF tăng; `QUORUM` và `ALL` thay đổi theo số replica.
- Không thể kỳ vọng `THREE` thành công nếu partition chỉ có RF = 2. Việc đặt ngưỡng cao hơn số replica được cấu hình không làm Cassandra tạo thêm replica.
- `ALL` là **mọi replica của partition theo replication strategy**, không phải mọi node trong toàn cluster.

## 4. Đọc/ghi ở RF = 3: cùng một dữ liệu, năm cách đợi

Giả sử partition của tài khoản `A-101` được nhân bản tới ba replica `R1`, `R2` và `R3`. Ứng dụng gửi lệnh cập nhật `display_name` thông qua coordinator.

```mermaid
sequenceDiagram
    participant C as Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3
    Note over C,R3: Ví dụ RF = 3, CL = TWO
    C->>R1: Gửi mutation
    C->>R2: Gửi mutation
    C->>R3: Gửi mutation
    R1-->>C: ACK (1)
    R2-->>C: ACK (2)
    Note over C: Đủ 2 ACK; trả thành công
    R3-->>C: ACK đến sau (nếu có)
```

Nếu **`R3` chậm hoặc mất kết nối**, kết quả của yêu cầu tùy CL:

| CL | Ngưỡng | Kết quả khi `R1` và `R2` phản hồi, `R3` không phản hồi |
| --- | ---: | --- |
| `ONE` | 1 | Có thể thành công sau phản hồi đầu tiên. |
| `TWO` | 2 | Có thể thành công. |
| `THREE` | 3 | Không đạt CL; thao tác thất bại/timeout. |
| `QUORUM` | 2 | Có thể thành công. |
| `ALL` | 3 | Không đạt CL; thao tác thất bại/timeout. |

Giả sử thêm `R2` cũng ngừng phản hồi, chỉ còn `R1`:

- `ONE` vẫn có thể trả về thành công nếu `R1` phản hồi đúng hạn.
- `TWO`, `THREE`, `QUORUM` và `ALL` đều không thể nhận đủ phản hồi theo ngưỡng đã chọn.

Với RF = 3, giả sử các replica còn lại hoạt động tốt, khả năng chịu lỗi replica theo ngưỡng phản hồi là:

| CL | Số replica tối đa có thể không phản hồi mà vẫn đạt CL |
| --- | ---: |
| `ONE` | **2** |
| `TWO` / `QUORUM` | **1** |
| `THREE` / `ALL` | **0** |

Đây là phép tính **khả năng đạt CL**: `RF - số ACK bắt buộc`. Nó không bảo đảm mọi lần đọc/ghi đều thành công, vì còn có lỗi coordinator, mạng, disk, timeout và ứng dụng.

### `ONE`: ưu tiên ít phản hồi, chấp nhận rủi ro đọc cũ

`ONE` hữu ích khi ứng dụng chấp nhận dữ liệu **eventually consistent**: ghi có thể nhanh hơn, đọc có thể hoàn tất khi chỉ một replica có mặt. Ví dụ danh sách sự kiện hoặc thông tin hiển thị có thể chấp nhận độ trễ cập nhật ngắn.

Nếu ghi mới chỉ được `R1` ACK mà lần đọc `ONE` lại lấy giá trị từ `R3` chưa bắt kịp, client **có thể thấy giá trị cũ**. Đọc `ONE` sau khi ghi `ONE` thành công không mặc nhiên bảo đảm **read-your-writes**.

### `TWO` và `THREE`: ngưỡng cố định

`TWO` yêu cầu hai ACK bất kể RF là 3, 4 hay 5. `THREE` yêu cầu ba ACK. Chúng hữu ích khi bạn cần kiểm soát **số phản hồi tuyệt đối**, nhưng tên mức này **không nói lên đa số** nếu RF thay đổi.

Ví dụ với RF = 5:

- `TWO`: 2/5 replica, **chưa phải đa số**.
- `THREE`: 3/5 replica, **đúng bằng quorum**.

Do đó, giả định “`TWO` luôn tương đương `QUORUM`” chỉ đúng về **ngưỡng số lượng** trong một số cấu hình, chẳng hạn RF = 3.

### `QUORUM`: đợi đa số replica

`QUORUM` yêu cầu `floor(RF / 2) + 1` ACK trong một datacenter; đa số này thay đổi cùng RF. Với RF = 3 cần 2; với RF = 5 cần 3. Một quorum không thể tách thành hai nhóm hoàn toàn không giao nhau trong cùng một tập replica.

Chính thuộc tính giao nhau này làm `QUORUM` trở thành lựa chọn phổ biến cho hệ thống cần cân bằng khả năng sẵn sàng và khả năng đọc thấy dữ liệu vừa được ghi thành công.

### `ALL`: chờ mọi replica

`ALL` chờ toàn bộ replica được cấu hình cho partition. Với RF = 3 phải đủ ba ACK; RF = 5 phải đủ năm ACK. Điều này khiến kết quả của một thao tác phụ thuộc cả replica chậm hoặc lỗi.

`ALL` không làm thao tác trở thành transaction đa hàng, không loại bỏ xung đột cập nhật đồng thời, và cũng không biến Cassandra thành hệ thống khóa toàn cục. Nó chỉ quy định **ngưỡng phản hồi** của yêu cầu.

## 5. Đọc mới đến đâu phụ thuộc cả CL ghi lẫn CL đọc

Lựa chọn CL **ghi** và **đọc** là hai quyết định riêng. Chỉ nhìn vào CL đọc sẽ không đủ để suy ra chắc chắn kết quả có mới hay không.

Gọi:

- `N`: tổng số replica của **cùng một partition trong cùng tập replica đang xét**;
- `W`: số replica đã xác nhận **ghi thành công**;
- `R`: số replica cần phản hồi cho lần **đọc**.

Nếu:

\[
R + W > N
\]

thì hai tập replica phải **giao nhau ở ít nhất một replica**.

Ví dụ **RF = 3**:

| CL ghi (`W`) | CL đọc (`R`) | `R + W` | Bảo đảm hai tập có giao nhau? |
| --- | --- | ---: | --- |
| `ONE` (1) | `ONE` (1) | 2 | Không. |
| `ONE` (1) | `QUORUM` (2) | 3 | Không. |
| `QUORUM` (2) | `QUORUM` (2) | 4 | **Có.** |
| `ALL` (3) | `ONE` (1) | 4 | **Có.** |
| `ONE` (1) | `ALL` (3) | 4 | **Có.** |
| `TWO` (2) | `THREE` (3) | 5 | **Có.** |

Giả sử ghi thành công ở `QUORUM`, không có ghi cạnh tranh và hai thao tác dùng cùng tập replica. Khi đọc `QUORUM`, ít nhất một replica phản hồi có mặt trong tập đã ACK ghi. Cassandra có thể sử dụng phiên bản đó trong quá trình reconcile để trả kết quả. Đây là nền tảng của mô hình **tunable consistency**.

**Nhưng giao nhau không đồng nghĩa với linearizability tổng quát.** Cần xét thêm cạnh tranh ghi đồng thời, timestamp, đồng hồ các node, quy tắc hòa giải last-write-wins, sự cố trong lúc xử lý và phạm vi replica. Quorum đọc/ghi thông thường không tự tạo transaction nguyên tử trên nhiều partition. Khi cần `INSERT ... IF NOT EXISTS` hoặc `UPDATE ... IF` để xử lý điều kiện cạnh tranh, hãy nghiên cứu **lightweight transaction (LWT)** dùng Paxos.

### Minh họa hai tập replica

```text
RF = 3:     R1     R2     R3

W = 2:      [x]    [x]     .
R = 2:       .     [x]    [x]
                    ^
           Có giao nhau tại R2

W = 1:      [x]     .      .
R = 2:       .     [x]    [x]

           Không giao nhau; lần đọc có thể cũ
```

Nếu đọc `QUORUM` nhưng lần ghi trước chỉ thành công ở `ONE`, **không thể** lấy lý do “đọc đa số” để kết luận chắc chắn sẽ thấy giá trị mới.

## 6. Khi có nhiều datacenter, đếm replica thế nào?

Giả sử keyspace sử dụng `NetworkTopologyStrategy`:

```text
dc1: RF = 3      A1  A2  A3
dc2: RF = 3      B1  B2  B3

Tổng số replica của một partition: N = 6
```

Năm CL trong bài là các mức **không yêu cầu số ACK cục bộ riêng biệt theo DC**:

| CL | Ngưỡng với RF toàn cục 6 | Ghi chú |
| --- | ---: | --- |
| `ONE` | **1** | Một replica bất kỳ phù hợp; không yêu cầu đa số ở DC hiện tại. |
| `TWO` | **2** | Hai replica; không buộc mỗi DC phải có ACK. |
| `THREE` | **3** | Ba replica; có thể đủ cả ba tại một DC. |
| `QUORUM` | **4** | Đa số của **cả sáu**; khi mỗi DC có ba replica, cần phản hồi từ cả hai DC. |
| `ALL` | **6** | Cần mọi replica ở cả hai DC. |

Lưu ý: Cassandra có thể **ưu tiên replica gần coordinator** để cải thiện độ trễ, nhưng `ONE`, `TWO` và `THREE` **không phải** các mức đảm bảo phản hồi thuộc DC cục bộ. Một lần `QUORUM` trong mô hình 3 + 3 thường phải chờ ít nhất một replica ở DC xa, làm độ trễ và tính sẵn sàng phụ thuộc kết nối liên vùng.

Nếu ứng dụng chạy nhiều datacenter và chỉ muốn đợi replica trong datacenter của coordinator, cần xem các mức **`LOCAL_ONE`** và **`LOCAL_QUORUM`**. Chẳng hạn, với RF = 3 tại `dc1`, `LOCAL_QUORUM` cần 2 ACK **ở dc1**, trong khi `QUORUM` trên cấu hình 3 + 3 cần 4 ACK **trong cả hai DC**.

Đừng áp dụng công thức `R + W > N` một cách máy móc khi ghi ở `LOCAL_QUORUM` của `dc1` nhưng đọc ở `LOCAL_QUORUM` của `dc2`: hai nhóm ACK có thể nằm ở hai DC **không giao nhau**. Tương tự, `EACH_QUORUM` là mức riêng dành cho **ghi** cần quorum tại từng DC, khác với `QUORUM` toàn cục.

## 7. Thực hành bằng CQL và `cqlsh`

Ví dụ tạo keyspace trên cụm **một datacenter** có tên thực là `dc1` và có đủ ít nhất ba node phù hợp:

```sql
CREATE KEYSPACE IF NOT EXISTS consistency_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS consistency_lab.profile_by_user (
  user_id uuid PRIMARY KEY,
  display_name text,
  city text
);
```

Bảng này truy vấn theo partition key `user_id`. RF = 3 đặt tại **keyspace**, còn CL được chọn **khi thực thi lệnh**.

Trong `cqlsh`, dùng lệnh `CONSISTENCY` để đặt CL mặc định cho những câu lệnh thực thi **sau đó trong phiên shell**:

```sql
CONSISTENCY ONE;

INSERT INTO consistency_lab.profile_by_user
    (user_id, display_name, city)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'An', 'Ha Noi'
);

CONSISTENCY TWO;

SELECT user_id, display_name, city
FROM consistency_lab.profile_by_user
WHERE user_id = 11111111-1111-4111-8111-111111111111;

CONSISTENCY QUORUM;

UPDATE consistency_lab.profile_by_user
SET city = 'Da Nang'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

CONSISTENCY ALL;

SELECT user_id, display_name, city
FROM consistency_lab.profile_by_user
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Với RF = 3:

- `INSERT` ở `ONE`: cần một replica ACK.
- `SELECT` ở `TWO`: cần hai replica phản hồi; vì lần ghi trước chỉ `ONE`, có thể xảy ra trường hợp không giao nhau.
- `UPDATE` ở `QUORUM`: cần hai replica ACK.
- `SELECT` ở `ALL`: cần cả ba replica phản hồi; sẽ thất bại nếu một replica không thể trả lời đúng hạn.

`CONSISTENCY` là **lệnh của `cqlsh`**, không phải cú pháp SQL gắn trực tiếp sau `INSERT` hay `SELECT`. Trong ứng dụng Java, driver thiết lập CL theo statement hoặc execution profile.

Có thể bật `TRACING ON;` trong `cqlsh` khi thử nghiệm một vài truy vấn nhỏ để quan sát quá trình thực thi, nhưng không nên suy ra rằng số sự kiện trace hoặc số request nội bộ luôn bằng số ACK tối thiểu của CL. Những lần thử có tác động nhất định lên cluster; dùng môi trường kiểm thử khi mô phỏng node lỗi.

## 8. Chọn CL trên từng yêu cầu bằng Java Driver 4.x

Apache Cassandra Java Driver cho phép đặt CL trên từng `Statement`. Ví dụ dưới đây dùng một `CqlSession` đã được khởi tạo, biết datacenter cục bộ và kết nối tới cluster:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.util.UUID;

public final class ProfileQueries {
    public static void updateCity(
            CqlSession session, UUID userId, String newCity) {
        SimpleStatement update = SimpleStatement.newInstance(
                "UPDATE consistency_lab.profile_by_user " +
                "SET city = ? WHERE user_id = ?",
                newCity, userId)
            .setConsistencyLevel(DefaultConsistencyLevel.QUORUM);

        session.execute(update); // RF=3 trong một DC: cần 2 ACK.
    }

    public static String findCity(CqlSession session, UUID userId) {
        SimpleStatement select = SimpleStatement.newInstance(
                "SELECT city FROM consistency_lab.profile_by_user " +
                "WHERE user_id = ?",
                userId)
            .setConsistencyLevel(DefaultConsistencyLevel.TWO);

        Row row = session.execute(select).one();
        return row == null ? null : row.getString("city");
    }
}
```

Khi đưa vào ứng dụng thực, nên dùng **`PreparedStatement` tái sử dụng** để giảm chi phí chuẩn bị câu lệnh, đồng thời cấu hình timeout/retry phù hợp với luồng nghiệp vụ. Các enum cùng nhóm gồm `DefaultConsistencyLevel.ONE`, `TWO`, `THREE`, `QUORUM` và `ALL`. Đổi CL trên statement **không sửa keyspace, bảng hoặc RF**.

Ví dụ trên minh họa cách đặt CL, không bảo đảm “đọc ngay luôn mới”: khi muốn đặt điều kiện giao nhau để đọc lại lần ghi mới nhất, hãy xét cả CL ghi, CL đọc và RF. Với RF = 3, `W=QUORUM=2` và `R=TWO=2` đáp ứng `R+W>3` nếu cả hai thao tác trên cùng tập replica và các giả định về cập nhật cạnh tranh được thỏa.

## 9. Chuyện gì xảy ra khi không đủ ACK?

**Không đủ phản hồi theo CL** khác với **chưa có replica nào xử lý thao tác**. Ví dụ ghi `ALL` với RF = 3:

1. `R1` nhận mutation và trả ACK.
2. `R2` nhận mutation và trả ACK.
3. `R3` không phản hồi trước deadline.
4. Client nhận lỗi timeout vì `ALL` đòi ba ACK, **dù `R1` và `R2` có thể đã ghi thành công**.

Phân biệt các nhóm lỗi thường thấy:

| Lỗi | Ý nghĩa điển hình | Hướng xử lý |
| --- | --- | --- |
| `Unavailable` | Coordinator xác định số replica khả dụng không đủ ngưỡng CL. | Kiểm tra RF, tình trạng replica, datacenter và mạng. |
| `WriteTimeout` | Không nhận đủ xác nhận ghi trong giới hạn thời gian. | Không giả định mutation chưa được áp dụng; cân nhắc retry an toàn. |
| `ReadTimeout` | Không nhận đủ phản hồi đọc kịp hạn, hoặc không hoàn tất đường đọc trong hạn. | Kiểm tra độ trễ, tải, replica, timeout và CL. |
| `ReadFailure` / `WriteFailure` | Replica báo lỗi trong quá trình xử lý khiến thao tác không thể đạt CL. | Điều tra log, node, tài nguyên và đường truy vấn. |

Nếu client tự động ghi lại sau timeout, có thể phát sinh vấn đề với **counter**, cập nhật không idempotent hoặc logic “gửi thông báo sau khi ghi”. Hãy thiết kế thao tác idempotent khi có thể, phân biệt lỗi khả dụng với timeout và đặt giới hạn retry.

Các cơ chế nền như **hinted handoff** và **repair** hỗ trợ replica bắt kịp hoặc đối chiếu dữ liệu; **compaction** quản lý SSTable/tombstone. Chúng **không thay thế** việc chọn CL đúng và cũng không bảo đảm rằng replica bị lỗi sẽ đồng bộ tức thời sau khi hồi phục.

## 10. Chọn mức nào cho tình huống thực tế?

| Tình huống | Mức thường cân nhắc | Lý do và giới hạn |
| --- | --- | --- |
| Truy vấn ít nhạy cảm với dữ liệu cũ, cần độ trễ thấp | `ONE` cho đọc và/hoặc ghi | Cần chấp nhận eventual consistency và có cách xử lý dữ liệu cũ. |
| RF = 3, cần cân bằng khả dụng và độ mới đọc/ghi | `QUORUM` cho cả hai chiều | 2 ACK mỗi chiều; có giao nhau theo cùng tập replica. |
| RF = 3, yêu cầu ghi thành công tại cả ba replica | `ALL` khi ghi | Dễ lỗi nếu một replica chậm/hỏng, chi phí phản hồi cao. |
| RF = 5, chỉ yêu cầu tối thiểu ba replica | `THREE` | 3/5 cũng là quorum khi RF = 5, nhưng không tự thích ứng nếu RF đổi. |
| Nhiều DC, ứng dụng muốn giảm độ trễ liên vùng | Xem `LOCAL_ONE`, `LOCAL_QUORUM` | Năm mức toàn cục trong bài không thể hiện ràng buộc đếm theo DC. |
| Cần cập nhật có điều kiện cạnh tranh | Xem LWT với `SERIAL`/`LOCAL_SERIAL` | Tăng CL thường không thay cho so sánh-và-ghi nguyên tử. |

Những tình huống trên là **điểm khởi đầu để thiết kế**, không phải cấu hình áp dụng tuyệt đối. Hãy kiểm tra độ trễ, tải thực tế, topology, lỗi replica và mong đợi của nghiệp vụ trước khi chọn.

## 11. Bài tập và đáp án

### Bài 1 — Tính ngưỡng

Một keyspace có RF = 5 trong một datacenter. Lần ghi đặt `THREE`, lần đọc đặt `QUORUM`.

**Câu hỏi:** Mỗi thao tác cần bao nhiêu phản hồi? Có bảo đảm tập ACK ghi và tập phản hồi đọc giao nhau không?

**Đáp án:** `THREE` cần 3 ACK; `QUORUM` với RF = 5 cũng cần `floor(5/2)+1=3` phản hồi. `3+3>5`, vì vậy hai tập bắt buộc giao nhau nếu cùng tập replica và thao tác ghi được xác nhận thành công.

### Bài 2 — Một replica không phản hồi

Một DC có RF = 3. `R1` và `R2` trả lời bình thường, `R3` mất kết nối.

**Câu hỏi:** `ONE`, `TWO`, `THREE`, `QUORUM` và `ALL` còn có thể thành công không?

**Đáp án:** `ONE`, `TWO` và `QUORUM` **có thể** thành công; `THREE` và `ALL` không đủ phản hồi. Điều này áp dụng cho cả đọc và ghi thông thường xét theo ngưỡng CL.

### Bài 3 — Thay RF

Hệ thống đang chạy RF = 3, với CL đọc `TWO`. Sau khi thay replication phù hợp thành RF = 5, nhóm phát triển giữ nguyên CL đọc.

**Câu hỏi:** `TWO` có còn tương đương `QUORUM` không?

**Đáp án:** Không. `TWO` vẫn cần đúng 2 phản hồi, còn `QUORUM` ở RF = 5 cần 3. Việc thay đổi topology/RF đòi hỏi rà lại giả định nhất quán.

### Bài 4 — Qua hai datacenter

`dc1` có RF = 3, `dc2` có RF = 3. Một lần ghi dùng `QUORUM`.

**Câu hỏi:** Tổng cộng cần bao nhiêu ACK? Chỉ nhận 3 ACK ở `dc1` thì đã đủ chưa?

**Đáp án:** Cần `floor(6/2)+1=4` ACK trên toàn bộ replica. Chỉ 3 ACK từ `dc1` **chưa đủ**; phải có ít nhất một ACK từ `dc2` trong topology này.

### Bài 5 — Timeout khi ghi

Ghi ở `ALL` với RF = 3, hai replica đã ACK, replica thứ ba timeout.

**Câu hỏi:** Có thể khẳng định dữ liệu chưa được ghi không?

**Đáp án:** Không. Lần ghi **không đạt CL** nên client nhận lỗi, nhưng hai replica có thể đã áp dụng mutation. Retry cần dựa trên tính idempotent và chính sách ứng dụng.

## 12. Những điều cần nhớ

1. `ONE`, `TWO`, `THREE` là **số ACK tuyệt đối**: 1, 2, 3.
2. `QUORUM` là **đa số**: `floor(RF/2)+1` (hoặc đa số trên tổng RF của các DC đối với `QUORUM` toàn cục).
3. `ALL` là **mọi replica của partition**, nên có độ nhạy cao với replica chậm hoặc lỗi.
4. CL ghi và CL đọc phải được thiết kế thành **một cặp**. Điều kiện `R+W>N` mô tả giao nhau của tập replica trong phạm vi thích hợp, nhưng không tự bảo đảm transaction/linearizability.
5. Chọn CL cao hơn có thể cải thiện khả năng thấy dữ liệu được xác nhận nhưng có thể làm tăng độ trễ và tỉ lệ lỗi; **CL không thay thế replication, repair, thiết kế bảng theo partition key hoặc xử lý lỗi ứng dụng**.

Khi xây dựng một dịch vụ Java dùng Cassandra, hãy bắt đầu bằng câu hỏi: *“Với RF và datacenter hiện có, một lần ghi cần bao nhiêu ACK và một lần đọc cần bao nhiêu phản hồi để đáp ứng nghiệp vụ?”* Từ đó mới chọn `ONE`, `TWO`, `THREE`, `QUORUM` hay `ALL` cho **từng truy vấn**, rồi kiểm chứng bằng tình huống mất replica và thử nghiệm tải thực tế.
