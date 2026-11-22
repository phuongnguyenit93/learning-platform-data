# Xử lý xóa đồng thời và cập nhật sau khi đối tượng đã bị xóa

Trong một ứng dụng nhiều người dùng, một đối tượng có thể được mở trên màn hình của nhiều người cùng lúc. Một người xóa đối tượng, trong khi người khác vẫn giữ bản dữ liệu cũ và cố gắng cập nhật nó. Nếu ứng dụng không kiểm tra trạng thái và phiên bản của đối tượng, thao tác cập nhật có thể thất bại âm thầm, ghi đè một thay đổi mới hơn hoặc thậm chí tạo lại đối tượng đã bị xóa.

Trong kiểm soát đồng thời lạc quan (Optimistic Concurrency Control), mỗi lần đọc có thể mang theo một phiên bản (version). Khi cập nhật hoặc xóa, ứng dụng chỉ thực hiện thao tác nếu phiên bản trong cơ sở dữ liệu vẫn bằng phiên bản mà nó đã đọc. **Xóa cũng là một thay đổi dữ liệu cần kiểm tra phiên bản; cập nhật từ một bản sao cũ phải thất bại khi đối tượng đã bị xóa hoặc đã thay đổi.**

## 1. Tình huống: một người xóa, người khác vẫn sửa

Giả sử hệ thống quản lý tài liệu có bản ghi:

| id | title | version |
|---:|---|---:|
| 42 | Kế hoạch triển khai | 7 |

Người dùng An và Bình cùng mở tài liệu `42`. Cả hai đều nhận nội dung với `version = 7`.

- An quyết định xóa tài liệu.
- Bình chưa biết tài liệu đã bị xóa và vẫn chỉnh sửa tiêu đề.

Nếu thao tác xóa của An thành công trước, ứng dụng phải xử lý yêu cầu cập nhật đến sau của Bình. Yêu cầu đó được tạo từ một đối tượng không còn tồn tại trong trạng thái hiện tại. Hệ thống không nên tự động xem nó là một tài liệu mới hoặc âm thầm báo cập nhật thành công.

Đây là một dạng xung đột giữa hai thao tác có ý nghĩa nghiệp vụ khác nhau: `DELETE` và `UPDATE`.

## 2. Vì sao cần version cho cả UPDATE và DELETE?

Một cột `version` cho phép ứng dụng phát hiện bản dữ liệu mà người dùng đang sửa đã cũ hay chưa.

Ví dụ cấu trúc bảng:

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT,
    version BIGINT NOT NULL DEFAULT 1
);
```

Khi đọc tài liệu, ứng dụng lấy cả `id`, nội dung và `version`. Khi cập nhật, ứng dụng đưa version đã đọc vào điều kiện `WHERE`:

```sql
UPDATE document
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Khi xóa, ứng dụng cũng dùng version đã đọc:

```sql
DELETE FROM document
WHERE id = :id
  AND version = :expected_version;
```

Ứng dụng kiểm tra số hàng bị tác động:

- `1` hàng: thao tác đã khớp với đối tượng và phiên bản mong đợi.
- `0` hàng: đối tượng không còn tồn tại hoặc version đã thay đổi. Thao tác không được xem là thành công theo điều kiện optimistic locking.

Với lệnh `DELETE`, không cần tăng version vì hàng bị xóa. Với lệnh `UPDATE`, version thường tăng sau mỗi lần cập nhật thành công để các bản đọc cũ không thể ghi tiếp.

## 3. Hai giao dịch cùng đọc một phiên bản

Giả sử An và Bình đều đọc `document 42` ở version `7`.

### Trường hợp A: thao tác xóa thắng trước

`T1` là giao dịch xóa của An; `T2` là giao dịch cập nhật của Bình.

```text
T1 (An)                                  T2 (Bình)
------------------------------------    ------------------------------------
Đã đọc document 42, version = 7         Đã đọc document 42, version = 7
DELETE WHERE id = 42 AND version = 7
1 hàng bị xóa
COMMIT
                                        UPDATE ...
                                        WHERE id = 42 AND version = 7
                                        0 hàng được cập nhật
```

Khi `T2` thực hiện cập nhật, hàng `42` đã biến mất. Điều kiện `WHERE` không còn khớp, nên số hàng cập nhật bằng 0. Ứng dụng nhận ra rằng bản dữ liệu Bình đang giữ đã lỗi thời hoặc đối tượng đã bị xóa.

### Trường hợp B: thao tác cập nhật thắng trước

Nếu `T2` cập nhật trước, version sẽ tăng từ `7` lên `8`:

```text
T2 (Bình)                                  T1 (An)
--------------------------------------    ------------------------------------
UPDATE ...
WHERE id = 42 AND version = 7
SET version = version + 1
1 hàng được cập nhật; version = 8
COMMIT
                                          DELETE
                                          WHERE id = 42 AND version = 7
                                          0 hàng bị xóa
```

Lệnh xóa của An không còn khớp version `7`. Nếu ứng dụng dùng optimistic locking đúng cách cho cả hai thao tác, việc cập nhật đã thắng trước sẽ khiến yêu cầu xóa dựa trên bản cũ thất bại. An cần tải lại trạng thái hiện tại và áp dụng chính sách xóa của ứng dụng.

Hai lịch trên cho thấy version tạo ra một điểm kiểm tra chung. Trong mỗi trường hợp, chỉ thao tác đầu tiên còn khớp version cũ mới có thể thành công; thao tác sau phải xử lý xung đột.

## 4. Điều gì xảy ra nếu chỉ UPDATE có version mà DELETE không có?

Nếu lệnh cập nhật có điều kiện version nhưng lệnh xóa chỉ dùng `id`, một lịch có thể xảy ra như sau:

1. `T1` đọc version `7` và muốn xóa.
2. `T2` đọc version `7`, cập nhật thành công và tăng version lên `8`.
3. `T1` chạy `DELETE FROM document WHERE id = 42`.
4. `T1` xóa luôn phiên bản `8` mà `T2` vừa ghi.

Đây là hành vi có thể đúng nếu nghiệp vụ quy định “yêu cầu xóa luôn có ưu tiên cuối cùng”, nhưng thường không phù hợp với optimistic locking vì thao tác xóa đã bỏ qua việc kiểm tra dữ liệu mà người dùng xác nhận xóa. Nếu mong muốn phát hiện mọi thay đổi kể từ lúc người dùng đọc, `DELETE` cũng phải chứa `version = :expected_version`.

Ngược lại, nếu chỉ DELETE có version mà UPDATE không có, một cập nhật cũ có thể ghi lên một phiên bản mới hơn khi hàng vẫn còn. Vì vậy, các thao tác ghi có thể cạnh tranh trên cùng đối tượng cần tuân theo một quy ước version nhất quán.

## 5. Đối tượng đã bị xóa: cập nhật phải xử lý ra sao?

Khi một yêu cầu cập nhật đến sau khi đối tượng đã bị xóa, có ba tình huống cần phân biệt:

1. **Đối tượng không tồn tại:** có thể đã bị xóa vật lý hoặc chưa từng tồn tại.
2. **Đối tượng tồn tại nhưng version đã thay đổi:** một giao dịch khác đã cập nhật trước.
3. **Đối tượng đã bị xóa mềm:** hàng vẫn còn trong bảng, nhưng trạng thái nghiệp vụ đánh dấu nó không còn hoạt động.

Ứng dụng không nên gộp cả ba tình huống thành “cập nhật thành công”. Nó cần phản ánh đúng kết quả cho người gọi và không ghi dữ liệu vào trạng thái đã bị xóa.

### Không tự động INSERT khi UPDATE không tìm thấy hàng

Một lỗi thường gặp là xử lý số hàng cập nhật bằng 0 bằng cách chạy `INSERT` hoặc `UPSERT` ngay lập tức. Điều này có thể vô tình tạo lại đối tượng mà người khác vừa xóa.

Ví dụ, nếu ứng dụng dùng `INSERT ... ON CONFLICT DO UPDATE` hoặc một hàm `save` có ngữ nghĩa upsert, một yêu cầu cũ có thể biến thành thao tác tạo mới. Khi đó, lệnh xóa trước đó không còn mang ý nghĩa như người dùng mong đợi.

Chỉ tạo lại đối tượng khi nghiệp vụ có một hành động “khôi phục” hoặc “tạo phiên bản mới” rõ ràng, có quyền hạn và kiểm tra trạng thái riêng. Một yêu cầu cập nhật thông thường không nên tự biến thành yêu cầu khôi phục.

### Không retry mù quáng cùng một payload cũ

Khi gặp optimistic lock conflict, retry cùng payload và cùng version thường chỉ thất bại lần nữa. Nguy hiểm hơn, nếu bỏ điều kiện version ở lần retry, ứng dụng có thể ghi đè dữ liệu mới hoặc hồi sinh trạng thái đã xóa.

Quy trình xử lý nên là:

1. Rollback transaction đã thất bại nếu DBMS yêu cầu.
2. Đọc lại trạng thái hiện tại theo một transaction mới.
3. Xác định đối tượng đã bị xóa, đã thay đổi version hay không còn quyền truy cập.
4. Trả lỗi phù hợp hoặc yêu cầu người dùng xem lại thay đổi.
5. Chỉ áp dụng lại ý định nghiệp vụ sau khi đã kiểm tra trạng thái mới; không tự động phát lại một bản ghi cũ.

## 6. Xóa vật lý và xóa mềm

### Xóa vật lý (hard delete)

Với hard delete, hàng bị loại khỏi bảng:

```sql
DELETE FROM document
WHERE id = :id
  AND version = :expected_version;
```

Sau khi commit, một câu `UPDATE` thông thường trên cùng `id` không tìm thấy hàng và tác động 0 hàng. Cách này ngăn cập nhật hàng đã xóa nếu ứng dụng kiểm tra row count và không dùng cơ chế tự tạo lại.

Hạn chế của hard delete là sau khi hàng biến mất, hệ thống thường không còn thông tin để phân biệt “chưa từng tồn tại” với “đã tồn tại nhưng bị xóa”. Nếu cần thông báo chính xác, audit hoặc đồng bộ với hệ thống khác, cần lưu lịch sử ở nơi khác hoặc dùng tombstone.

### Xóa mềm (soft delete)

Với soft delete, hàng vẫn còn nhưng được đánh dấu đã xóa:

```sql
ALTER TABLE document
ADD COLUMN deleted_at TIMESTAMP NULL;
```

Thao tác xóa có thể là:

```sql
UPDATE document
SET deleted_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :id
  AND version = :expected_version
  AND deleted_at IS NULL;
```

Mọi cập nhật thông thường phải loại trừ hàng đã xóa:

```sql
UPDATE document
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND version = :expected_version
  AND deleted_at IS NULL;
```

Nếu lệnh xóa mềm đã thành công, `version` tăng và `deleted_at` khác `NULL`. Một lệnh cập nhật cũ không khớp cả hai điều kiện `version` và `deleted_at IS NULL`, do đó không thể sửa đối tượng đã xóa.

**Điểm dễ bỏ sót:** nếu mọi truy vấn cập nhật không thêm điều kiện `deleted_at IS NULL`, hàng đã xóa mềm vẫn có thể bị thay đổi. Cần đặt quy tắc này ở tầng truy cập dữ liệu hoặc repository dùng chung, đồng thời bảo đảm các câu SQL đặc biệt cũng tuân theo.

## 7. Tombstone giúp phân biệt đã xóa và chưa từng tồn tại

Tombstone (bản ghi đánh dấu đã xóa) là thông tin tối thiểu được giữ lại sau khi đối tượng bị xóa. Nó có thể nằm trong chính bảng dưới dạng `deleted_at`, hoặc ở bảng lịch sử riêng.

Ví dụ một cấu trúc soft-delete có thêm người xóa:

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by BIGINT NULL
);
```

Tombstone có thể giúp hệ thống:

- Phân biệt một id đã bị xóa với một id chưa từng tồn tại.
- Trả lời yêu cầu cập nhật cũ bằng trạng thái “đã xóa”.
- Ghi audit, người xóa và thời điểm xóa.
- Đồng bộ sự kiện xóa đến cache, search index hoặc dịch vụ khác.
- Ngăn một bản sao dữ liệu cũ tự tạo lại đối tượng trong quá trình đồng bộ.

Tombstone cần chính sách lưu giữ và dọn dẹp. Nếu xóa tombstone quá sớm, một thiết bị offline hoặc một message cũ có thể quay lại sau thời gian dài mà hệ thống không còn dấu vết để nhận biết đối tượng đã bị xóa.

## 8. Nguy cơ ABA khi tái sử dụng ID

Giả sử đối tượng `id = 42`, `version = 1` bị xóa. Sau đó, hệ thống tạo một đối tượng hoàn toàn mới nhưng tái sử dụng `id = 42` và đặt version trở lại `1`.

Một client cũ vẫn giữ payload `id = 42, version = 1`. Khi gửi cập nhật, điều kiện `WHERE id = 42 AND version = 1` có thể khớp với đối tượng mới, dù client cũ đang nói về đối tượng trước khi xóa.

Đây là một dạng ABA problem: giá trị định danh/phiên bản quay lại trạng thái giống trước đó, khiến thao tác cũ tưởng rằng đối tượng vẫn là đối tượng ban đầu.

Có thể phòng tránh bằng cách:

- Không tái sử dụng ID của đối tượng đã xóa.
- Dùng ID mới (chẳng hạn UUID) cho một vòng đời đối tượng mới.
- Dùng một `generation` hoặc `incarnation_id` bất biến và đưa nó vào điều kiện cập nhật cùng version.
- Nếu dùng tombstone, chỉ khôi phục qua thao tác restore tường minh và tăng version/generation theo quy tắc riêng.

Ví dụ điều kiện cập nhật mạnh hơn:

```sql
UPDATE document
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND incarnation_id = :expected_incarnation
  AND version = :expected_version
  AND deleted_at IS NULL;
```

Ngay cả khi `id` được tái sử dụng do yêu cầu nghiệp vụ, `incarnation_id` khác nhau sẽ ngăn request thuộc vòng đời cũ cập nhật nhầm đối tượng mới.

## 9. Ánh xạ với JPA/Hibernate bằng @Version

Trong JPA, có thể dùng `@Version` để bật optimistic locking cho entity:

```java
@Entity
public class Document {

    @Id
    private Long id;

    private String title;

    @Version
    private Long version;
}
```

Provider sẽ dùng version trong câu SQL cập nhật hoặc xóa theo cơ chế của nó. Một câu cập nhật về mặt khái niệm có dạng:

```sql
UPDATE document
SET title = ?, version = 8
WHERE id = 42
  AND version = 7;
```

Nếu hàng đã bị xóa hoặc version đã đổi, số hàng tác động không khớp với kỳ vọng và provider báo optimistic locking failure, thường thông qua `OptimisticLockException` hoặc ngoại lệ được framework bao bọc như `ObjectOptimisticLockingFailureException` trong Spring.

Một số điểm cần chú ý:

- `@Version` phải được ánh xạ đúng vào cột version do ORM quản lý; không tự sửa version bằng code ứng dụng trong các thao tác thông thường.
- Lỗi có thể xuất hiện khi `flush()` hoặc `commit()`, không nhất thiết ngay tại lời gọi `save()`.
- Entity đã bị xóa trong database nhưng vẫn còn trong persistence context không có nghĩa nó còn hợp lệ để cập nhật. Khi flush, ORM có thể phát hiện row count không khớp và ném optimistic locking exception.
- Bulk JPQL/SQL update hoặc delete thường bỏ qua cơ chế dirty checking/version tự động của entity. Nếu dùng bulk operation, phải tự thêm điều kiện version, xử lý row count và đồng bộ/clear persistence context phù hợp.
- Không bắt `OptimisticLockException` rồi bỏ qua. Cần rollback transaction và chuyển thành phản hồi nghiệp vụ phù hợp.

## 10. Trả kết quả cho API và giao diện

Một API cập nhật có thể nhận version từ client thông qua trường `version` trong request hoặc HTTP ETag/`If-Match`.

Ví dụ payload:

```json
{
  "id": 42,
  "version": 7,
  "title": "Kế hoạch đã chỉnh sửa"
}
```

Nếu dùng ETag, server trả về một định danh phiên bản trong header khi đọc tài nguyên; client gửi lại `If-Match` khi cập nhật hoặc xóa. Nếu tài nguyên đã thay đổi hoặc bị xóa, điều kiện không còn khớp và server từ chối thao tác có điều kiện.

Các phản hồi thường gặp tùy hợp đồng API:

| Trạng thái | Ý nghĩa có thể dùng |
|---|---|
| `404 Not Found` | Đối tượng hiện không tồn tại hoặc server không muốn tiết lộ sự tồn tại của nó |
| `410 Gone` | Server biết đối tượng đã bị xóa và muốn thông báo rõ trạng thái này |
| `409 Conflict` | Thao tác xung đột với trạng thái hiện tại của tài nguyên |
| `412 Precondition Failed` | Điều kiện `If-Match`/precondition của request không còn đúng |

Không có một mã duy nhất bắt buộc cho mọi thiết kế. Hãy chọn hợp đồng nhất quán: nếu version mismatch được biểu diễn bằng `412`, hãy dùng nhất quán cho cả cập nhật và xóa có điều kiện; nếu đối tượng đã bị xóa và API có tombstone, có thể trả `410` theo thiết kế.

Ở giao diện, nên thông báo rằng tài liệu đã bị xóa hoặc đã thay đổi bởi người khác, sau đó làm mới dữ liệu. Không nên tự động gửi lại nội dung cũ với version mới nếu chưa có quy tắc hợp nhất rõ ràng.

## 11. Xóa lặp lại và tính idempotent

Người dùng có thể nhấn nút xóa hai lần, client retry sau timeout hoặc một message xóa được giao nhiều lần. Ứng dụng cần quyết định cách xử lý lệnh xóa lặp lại.

Với hard delete, lần xóa đầu có thể tác động 1 hàng; lần sau tác động 0 hàng vì đối tượng đã biến mất. Với soft delete, lần đầu cập nhật `deleted_at`; lần sau không còn khớp `deleted_at IS NULL`.

Hai cách phản hồi phổ biến:

- **Strict result:** lần xóa thứ hai trả “không tìm thấy” hoặc “đã bị xóa”, giúp caller nhận biết trạng thái.
- **Idempotent command:** nếu mục tiêu của API là “đảm bảo đối tượng không còn hoạt động”, có thể trả kết quả thành công khi đối tượng đã ở trạng thái xóa. Cần bảo đảm hành vi này không che giấu việc một id chưa từng tồn tại nếu điều đó quan trọng với nghiệp vụ.

Idempotency của thao tác xóa không có nghĩa là mọi thao tác cập nhật sau đó cũng được chấp nhận. Một lệnh cập nhật đến sau vẫn phải kiểm tra rằng đối tượng còn tồn tại, chưa bị xóa và version còn phù hợp.

## 12. Xóa đối tượng có quan hệ và tác động phụ

Một đối tượng có thể được tham chiếu bởi đơn hàng, bình luận, file hoặc bản ghi con. Xóa đối tượng cha có thể kích hoạt foreign key, `ON DELETE CASCADE`, trigger hoặc quy trình dọn dẹp riêng.

Khi có cập nhật đồng thời trên bản ghi cha và bản ghi con, cần xác định:

- Transaction nào sở hữu việc xóa và cập nhật từng bản ghi.
- Foreign key ngăn bản ghi con tham chiếu đến cha đã xóa như thế nào.
- Cascade delete có phù hợp với dữ liệu lịch sử hay nên dùng soft delete/archival.
- Các thao tác cần thành công cùng nhau có nằm trong một transaction hay không.
- Cache, search index và dịch vụ bên ngoài nhận sự kiện xóa sau khi commit như thế nào.

Không nên gửi sự kiện “đã xóa” trước khi transaction xóa commit thành công. Nếu cần bảo đảm sự kiện được phát sau commit, transactional outbox là một mẫu thiết kế thường dùng: ghi bản ghi outbox trong cùng transaction với thao tác xóa, rồi worker phát sự kiện sau đó.

## 13. Quy trình xử lý xung đột đề xuất

Khi một thao tác cập nhật hoặc xóa không tác động hàng nào, hãy xử lý theo quy trình có chủ đích:

1. **Kiểm tra kết quả SQL/ORM:** xác định thao tác có tác động đúng một hàng hay không. Với cập nhật một đối tượng theo khóa chính, số hàng mong đợi thường là 1.
2. **Kết thúc transaction hiện tại:** rollback nếu có optimistic lock failure hoặc lỗi transaction.
3. **Đọc lại trạng thái:** tìm đối tượng theo id và, nếu có, cả incarnation/generation.
4. **Phân loại:** đã bị xóa, không tồn tại từ trước, version mới hơn, hoặc không còn quyền truy cập.
5. **Phản hồi:** trả lỗi xung đột/đã xóa phù hợp; yêu cầu người dùng làm mới hoặc xác nhận hành động mới.
6. **Chỉ retry khi an toàn:** retry toàn bộ nghiệp vụ với dữ liệu mới nếu chính sách cho phép; không bỏ qua version và không biến update thành upsert ngoài ý muốn.

Nếu cần phân biệt chính xác “đã xóa” với “không tồn tại”, hãy lưu tombstone hoặc audit record. Với hard delete thuần túy, row count bằng 0 chỉ cho biết điều kiện không còn khớp; nó không đủ để xác định nguyên nhân.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Chỉ UPDATE mới cần kiểm tra version. | DELETE cũng phải kiểm tra version nếu cần phát hiện thay đổi kể từ lúc người dùng đọc. |
| Xóa thành công thì client cũ có thể cập nhật lại nếu còn id. | Hàng đã xóa không còn khớp; không tự động tạo lại bằng INSERT/UPSERT. |
| UPDATE tác động 0 hàng luôn có nghĩa version conflict. | Có thể là id không tồn tại, đã bị xóa hoặc version không còn khớp. Cần phân loại nếu nghiệp vụ cần. |
| Soft delete không cần điều kiện đặc biệt khi UPDATE. | UPDATE phải loại trừ hàng có `deleted_at IS NOT NULL` và kiểm tra version. |
| Retry bằng cách bỏ version sẽ giải quyết xung đột. | Cách đó có thể ghi đè dữ liệu mới hoặc hồi sinh đối tượng đã xóa. |
| Dùng `@Version` bảo vệ mọi câu SQL. | Bulk SQL/JPQL có thể bỏ qua cơ chế version tự động; cần tự quản lý điều kiện và row count. |
| Có thể tái sử dụng id và reset version an toàn. | Request cũ có thể khớp đối tượng mới; dùng id mới hoặc incarnation/generation. |

## 15. Tự kiểm tra

**Tình huống 1:** An và Bình cùng đọc tài liệu ở version `7`. An xóa bằng `DELETE WHERE id = 42 AND version = 7` và commit. Bình cập nhật bằng `UPDATE ... WHERE id = 42 AND version = 7`. Kết quả của Bình là gì?

**Đáp án:** Câu UPDATE tác động 0 hàng vì tài liệu đã bị xóa. Ứng dụng phải xử lý trạng thái đối tượng đã biến mất hoặc xung đột, không báo cập nhật thành công.

**Tình huống 2:** Bình cập nhật version `7` thành `8` trước. An xóa với điều kiện `version = 7`. Điều gì xảy ra?

**Đáp án:** DELETE tác động 0 hàng vì version hiện tại là `8`. An cần tải lại trạng thái và áp dụng chính sách xóa; không thể coi yêu cầu cũ là đã xóa thành công.

**Tình huống 3:** Bảng dùng soft delete. Lệnh UPDATE chỉ có `WHERE id = :id AND version = :version`, không có `deleted_at IS NULL`. Có rủi ro gì?

**Đáp án:** Nếu version được truyền đúng thì lệnh cũ thường không khớp sau khi xóa mềm đã tăng version. Tuy nhiên, một client đọc được version mới của hàng đã xóa hoặc một luồng ghi bỏ qua quy tắc nghiệp vụ vẫn có thể cập nhật hàng đó. Điều kiện `deleted_at IS NULL` cần được áp dụng như một hàng rào rõ ràng cho mọi cập nhật thông thường.

**Tình huống 4:** Sau khi xóa `id = 42`, hệ thống tạo tài liệu mới với cùng id và reset version về `1`. Một client cũ đang giữ `id = 42, version = 1` gửi cập nhật. Vì sao nguy hiểm?

**Đáp án:** Điều kiện id/version có thể khớp tài liệu mới dù client cũ đang nói về vòng đời cũ. Không tái sử dụng id hoặc bổ sung incarnation/generation bất biến vào điều kiện cập nhật.

**Tình huống 5:** ORM dùng `@Version`, nhưng một câu bulk JPQL xóa nhiều bản ghi không kiểm tra version. Có thể dựa vào `@Version` để bảo vệ câu lệnh đó không?

**Đáp án:** Không nên giả định như vậy. Bulk operation thường bỏ qua cơ chế version tự động của entity. Cần thêm điều kiện version phù hợp, kiểm tra số hàng tác động và đồng bộ persistence context.

Khi xử lý xóa đồng thời, hãy xem xóa là một lần thay đổi phiên bản của đối tượng. Mọi cập nhật hoặc xóa dựa trên bản đọc cũ phải kiểm tra lại trạng thái hiện tại; nếu đối tượng đã biến mất hoặc đã chuyển sang trạng thái deleted, yêu cầu cũ phải được từ chối hoặc xử lý qua một luồng restore tường minh.
