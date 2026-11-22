# Dữ liệu thêm, xóa giữa các trang và tính nhất quán khi duyệt

## 1. Vấn đề thực tế: một tập hợp không đứng yên

Trong REST API, endpoint `GET /orders` thường trả một phần danh sách vì số đơn hàng quá lớn để tải hết trong một lần. Client xem trang đầu, sau đó yêu cầu trang tiếp theo. Trong khoảng thời gian giữa hai request, hệ thống vẫn có thể **tạo đơn mới, xóa đơn, sửa trạng thái, thay đổi trường sắp xếp hoặc quyền truy cập**. Vì thế trang thứ hai không nhất thiết được tính từ cùng một tập dữ liệu như trang đầu.

Khi mới triển khai phân trang, lập trình viên thường chỉ kiểm tra rằng `limit=20` trả tối đa 20 phần tử. Một API dùng trong thực tế còn phải trả lời: nếu bản ghi xuất hiện hoặc biến mất giữa các lần gọi, client có nhìn thấy bản ghi bị lặp? Có bỏ sót bản ghi? Tập kết quả đang biểu diễn một ảnh chụp nhất quán hay là dữ liệu mới nhất ở mỗi lần gọi?

Bài học thuộc chương **Truy vấn tập hợp** của học phần `INTEGRATION_API_REST`. Nó kết nối thiết kế resource, URI, HTTP method, status code và hợp đồng dữ liệu với phân trang, cache, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử REST API bằng Java/Spring hoặc công nghệ tương đương.

Sau bài học, người học có thể:

1. Tái hiện trường hợp **trùng, bỏ sót hoặc xuất hiện bản ghi mới** khi duyệt nhiều trang.
2. Phân biệt phân trang theo vị trí (**OFFSET/LIMIT**) và theo khóa (**cursor/keyset**).
3. Thiết kế thứ tự sắp xếp toàn phần, ổn định và cursor không phụ thuộc vị trí của phần tử.
4. Phát biểu rõ hợp đồng nhất quán: **live**, **có mốc giới hạn** (*anchored*) hoặc **snapshot**.
5. Hiểu giới hạn của cursor khi bản ghi bị xóa, đổi trường sort, đổi bộ lọc hoặc quyền truy cập.
6. Cài đặt keyset pagination và kiểm thử thay đổi dữ liệu giữa các request bằng PostgreSQL, Java/Spring.
7. Tài liệu hóa giới hạn, định dạng phản hồi và cách khôi phục khi cursor hết hạn hoặc không hợp lệ.

## 2. Ví dụ gốc: duyệt đơn hàng theo thời điểm tạo

Giả sử API trả các đơn theo `createdAt DESC, id DESC`, mỗi trang hai phần tử. Để dễ theo dõi, ví dụ dùng một khóa thứ tự đơn giản và các ID A–E:

| Vị trí ban đầu | ID | createdAt |
| ---: | --- | --- |
| 0 | A | 10:00 |
| 1 | B | 09:00 |
| 2 | C | 08:00 |
| 3 | D | 07:00 |
| 4 | E | 06:00 |

Một lượt đọc khi **không có thay đổi**:

```http
GET /orders?limit=2&offset=0 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{"items":[{"id":"A"},{"id":"B"}],"nextOffset":2}
```

```http
GET /orders?limit=2&offset=2 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{"items":[{"id":"C"},{"id":"D"}],"nextOffset":4}
```

Trong trạng thái tĩnh, client thấy `A, B, C, D, E` qua ba trang mà không trùng hoặc thiếu. Nhưng mỗi request HTTP thông thường là một giao dịch riêng: truy vấn trang thứ hai sẽ chạy lại trên **dữ liệu ở thời điểm khác**.

### Giả định cần giữ trong mọi ví dụ

- API luôn có một thứ tự sắp xếp được quy định. Không có `ORDER BY` thì CSDL không cam kết thứ tự hàng; so sánh các trang gần như vô nghĩa.
- Dữ liệu cho phép khách hàng nhìn thấy đã được giới hạn bởi tenant và quyền truy cập.
- Ví dụ bỏ qua một số điều kiện nghiệp vụ để tập trung vào sự thay đổi vị trí.
- Khi nói “bỏ sót” hoặc “trùng”, ta xét một **lượt duyệt** bắt đầu ở trang 1 rồi đi tiếp, không phải một GET đơn lẻ.

## 3. OFFSET/LIMIT: thêm trước vị trí hiện tại gây trùng

Sau khi client nhận trang 1 là `[A, B]`, một người dùng khác thêm đơn `X` lúc 09:30. Tập hợp hiện tại trở thành:

```text
Trước insert:  A B C D E
                ^ ^
             Trang 1: A B

Sau insert:   A X B C D E
                    ^ ^
             OFFSET 2: B C
```

Trang thứ hai trả `[B, C]`, khiến client thấy `B` **hai lần**:

```text
Đã nhận:       A, B
Trang 2:       B, C
Kết quả duyệt: A, B, B, C ...
```

Lý do: `OFFSET 2` bỏ qua **hai phần tử đang đứng đầu ở thời điểm truy vấn thứ hai**, không có nghĩa “tiếp tục sau bản ghi B”. Bản ghi `X` mới đã đẩy B từ vị trí 1 sang vị trí 2.

### Một trang với OFFSET không tự lưu trạng thái

Ví dụ SQL:

```sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 2;
```

Câu lệnh chỉ biết số phần tử cần bỏ qua, không biết ID nào client đã xem trước đó. Transaction của request trước đã kết thúc, nên dù cơ sở dữ liệu hỗ trợ MVCC thì trang thứ hai thường vẫn nhìn thấy một trạng thái mới.

## 4. OFFSET/LIMIT: xóa trước vị trí hiện tại gây bỏ sót

Quay lại tập hợp **ban đầu** `A, B, C, D, E`. Client đã nhận trang 1 `[A, B]`. Sau đó đơn `A` bị xóa khỏi tập kết quả trước khi client gọi trang 2.

```text
Trước delete:  A B C D E
                ^ ^
             Trang 1: A B

Sau delete:   B C D E
                  ^ ^
             OFFSET 2: D E
```

Trang thứ hai trả `[D, E]`. Bản ghi `C` vẫn tồn tại nhưng **không bao giờ được client nhìn thấy trong lượt duyệt này**. Việc xóa A đã làm C dời từ vị trí 2 sang vị trí 1 và bị OFFSET bỏ qua.

| Biến cố giữa hai trang | Trang 1 | Dữ liệu khi gọi trang 2 | Trang 2 OFFSET 2 | Hậu quả |
| --- | --- | --- | --- | --- |
| Không thay đổi | A, B | A, B, C, D, E | C, D | Không bất thường |
| Thêm X giữa A và B | A, B | A, X, B, C, D, E | B, C | **B bị lặp** |
| Xóa A | A, B | B, C, D, E | D, E | **C bị bỏ sót** |
| Xóa B | A, B | A, C, D, E | D, E | **C bị bỏ sót** |

Những lỗi này không đồng nghĩa SQL chạy sai. Mỗi câu SELECT đều trả kết quả đúng với tập dữ liệu ở **thời điểm riêng** của nó. Vấn đề nằm ở **hợp đồng duyệt xuyên nhiều request**.

## 5. Bản ghi đổi vị trí do cập nhật còn phức tạp hơn thêm và xóa

Không chỉ insert/delete, một bản ghi có thể bị di chuyển giữa các trang khi:

- API sắp xếp theo `updatedAt DESC` và một bản ghi cũ được sửa.
- API lọc `status=OPEN` rồi đơn chuyển sang `CLOSED`.
- Giá hoặc điểm xếp hạng thay đổi trong danh sách `sort=price` hay `sort=score`.
- Quy tắc phân quyền thay đổi, khiến một bản ghi được hiển thị hoặc bị ẩn giữa hai request.

Ví dụ client đã xem `A, B`, nhưng bản ghi `D` được cập nhật để `updatedAt` mới hơn A. D sẽ nhảy lên đầu; OFFSET có thể tạo lặp/thiếu giống trường hợp insert. **Cursor cũng không bảo đảm tính nhất quán** nếu khóa sắp xếp của bản ghi được phép đổi: một item đã đọc có thể di chuyển xuống phía sau cursor và xuất hiện lại, còn một item chưa đọc có thể nhảy lên trước cursor và bị bỏ qua.

Do đó câu hỏi thiết kế không chỉ là **“OFFSET hay cursor?”** mà còn là **“đang sắp xếp theo thuộc tính nào, thuộc tính đó có thay đổi không, và cần mức nhất quán nào?”**

## 6. Cursor/keyset: tiếp tục sau một khóa, không tiếp tục sau một vị trí

Với keyset pagination, client gửi **khóa của phần tử cuối trang trước** thay vì gửi số hàng đã bỏ qua. Ví dụ trang 1 là `A (10:00), B (09:00)`; cursor của trang tiếp theo mang ý nghĩa “lấy các đơn có khóa sắp xếp **nhỏ hơn khóa B**”.

```sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
```

Với `created_at DESC, id DESC`, điều kiện tuple `(created_at,id) < (...)` tiếp tục theo thứ tự giảm dần. Trong PostgreSQL, phép so sánh tuple với kiểu cột tương thích được hỗ trợ. Một CSDL khác có thể cần điều kiện tương đương:

```sql
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at AND id < :last_id)
```

Điều kiện trên là phần **bộ lọc keyset**; trong truy vấn thật phải kết hợp với `tenant_id`, quyền truy cập, các filter và `ORDER BY` giống nhau trên tất cả các trang. Khi có các chiều sắp xếp ASC/DESC hỗn hợp hoặc giá trị NULL, cần thiết kế bộ so sánh tương ứng thay vì sao chép nguyên tuple predicate.

### Minh họa với dữ liệu thay đổi

Giữ trang 1 `[A, B]`, cursor ghi khóa của B là 09:00:

| Biến cố trước trang 2 | Tập hiện tại | Trang 2 với điều kiện “sau B” | Nhận xét |
| --- | --- | --- | --- |
| Không thay đổi | A, B, C, D, E | C, D | Tiếp tục ổn định |
| Thêm X lúc 09:30, trước B | A, X, B, C, D, E | C, D | **Không lặp B**; X không nằm trong phần còn lại |
| Xóa A | B, C, D, E | C, D | **Không bỏ sót C** do dịch chuyển vị trí |
| Xóa B | A, C, D, E | C, D | Cursor vẫn có khóa B dù bản ghi B đã bị xóa |
| Thêm Y lúc 08:30, sau B | A, B, Y, C, D, E | Y, C | **Y mới có thể xuất hiện** trong lượt duyệt |

**Kết luận chính xác:** keyset giúp tránh trùng/bỏ sót **do phần tử dịch chuyển vị trí khi có thêm/xóa trước khóa cursor**, với điều kiện thứ tự ổn định và khóa duy nhất. Nó **không tự tạo snapshot** của toàn bộ tập hợp. Một phần tử mới nằm **sau** cursor vẫn có thể xuất hiện trong trang tiếp theo.

## 7. Thứ tự toàn phần: vì sao cần tie-breaker?

Chỉ sắp xếp theo `createdAt DESC` chưa đủ nếu nhiều bản ghi được tạo trong cùng một mili-giây hoặc cùng độ phân giải timestamp. Hai đơn có `createdAt` bằng nhau sẽ không có thứ tự xác định, khiến cursor có thể bỏ sót hoặc lặp khi chuyển trang.

Ví dụ:

```text
A: createdAt = 10:00:00.000
B: createdAt = 10:00:00.000
C: createdAt = 09:59:59.000
```

Nếu trang 1 chỉ có A và cursor lưu mỗi timestamp 10:00:00.000, truy vấn tiếp theo `createdAt < 10:00:00.000` sẽ bỏ B dù B chưa được xem.

Thiết kế thứ tự:

```sql
ORDER BY created_at DESC, id DESC
```

Kết hợp `created_at` với `id` **duy nhất, không NULL và không đổi** cho phép xác định thứ tự toàn phần. Cursor phải lưu **cả hai giá trị**, không chỉ timestamp. Nếu business sort theo giá, điểm hoặc tên, vẫn cần tie-breaker duy nhất, đồng thời xem xét tính thay đổi được của khóa sort.

### Những điều cần chốt

1. **Khóa sắp xếp:** nêu rõ danh sách cột, chiều ASC/DESC và quy tắc NULL.
2. **Tính duy nhất:** khóa cuối cùng phải có tie-breaker đủ tạo thứ tự toàn phần.
3. **Tính bất biến:** nếu trường sort có thể đổi, thiết kế cần nhận diện điều đó trong hợp đồng nhất quán.
4. **Chỉ mục:** index phù hợp với bộ lọc, thứ tự và khóa cursor để tránh scan/sort lớn.
5. **Lọc:** sử dụng cùng ngữ nghĩa filter và phân quyền tại mỗi request; không được lấy dữ liệu ngoài phạm vi chỉ vì cursor cũ.

## 8. Ba mức nhất quán cần công bố cho lượt duyệt

Không có một kiểu phân trang luôn đúng cho mọi yêu cầu. REST API cần nói rõ **người dùng có thể kỳ vọng điều gì khi dữ liệu thay đổi**.

| Mức | Hợp đồng minh họa | Khi phù hợp | Giới hạn |
| --- | --- | --- | --- |
| **Live pagination** | Mỗi request lấy dữ liệu hiện có theo filter/sort; không cam kết cùng một snapshot | Feed, sản phẩm, dashboard cập nhật liên tục | Tập kết quả có thể thay đổi giữa các trang |
| **Anchored / bounded pagination** | Lượt duyệt có một **mốc giới hạn trên** của khóa sắp xếp; các trang sau không vượt mốc đó | Duyệt dữ liệu được tạo theo trình tự ổn định, tránh item mới nằm trước đầu danh sách | Không bảo đảm snapshot nếu item mới có khóa nằm trong khoảng cũ, bản ghi bị sửa/xóa hoặc khóa không phản ánh thứ tự commit |
| **Snapshot pagination** | Toàn bộ trang trong một lượt đọc từ **một phiên bản logic xác định** của tập dữ liệu | Xuất báo cáo, đối soát, công việc không được bỏ sót dữ liệu tại thời điểm chọn | Tốn tài nguyên/lưu lịch sử; cần quản lý TTL, quyền và xóa dữ liệu |

**Đừng gọi kết quả “snapshot” chỉ vì cursor chứa một timestamp.** Timestamp có thể là mốc lọc, không phải ảnh chụp CSDL. Với bản ghi được sửa hoặc xóa sau thời điểm đó, truy vấn bình thường trên bảng hiện tại không thể tái dựng giá trị của chúng trước khi thay đổi nếu không có lịch sử hoặc cơ chế snapshot tương đương.

### 8.1. Live: trả dữ liệu mới nhất tại từng lần gọi

Ví dụ client duyệt danh sách sản phẩm có giá và tình trạng tồn kho thường xuyên thay đổi. Mức live phù hợp khi client hiểu rằng:

- Mỗi trang được tính từ dữ liệu có thể đã thay đổi.
- Không cam kết tổng số trang cố định.
- Có thể có bản ghi mới, biến mất hoặc được sửa trong lúc duyệt.
- Nút “Làm mới” hoặc việc bắt đầu lại từ trang đầu là hành vi bình thường.

Với sort ổn định và keyset, nguy cơ trùng/bỏ sót do dịch chuyển vị trí giảm đáng kể. Tuy vậy API phải nói rõ mức đảm bảo thực tế, nhất là khi filter/sort động.

### 8.2. Anchored: cố định một giới hạn trên

Một danh sách đơn hàng sắp xếp theo khóa tạo bất biến có thể đóng băng **khóa cao nhất nhìn thấy ở lần đọc đầu**. Cursor về sau mang hai mốc:

- `anchorKey`: khóa cao nhất được phép xuất hiện trong lượt duyệt.
- `lastKey`: khóa cuối của trang đã trả; lần tiếp theo chỉ lấy phần tử sau khóa này.

```sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND (created_at, id) <= (:anchor_created_at, :anchor_id)
  AND (created_at, id) <  (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
```

Trong dữ liệu được tạo với khóa tăng đều, insert mới thường nằm **trước anchor** và sẽ bị loại. Nhưng hãy xét một giao dịch được commit muộn có `createdAt` cũ, bản ghi được nhập lịch sử, hoặc timestamp được cung cấp từ client: item mới vẫn có thể nằm **dưới anchor** và lọt vào các trang kế tiếp. Ngay cả sequence ID tăng cũng không mặc nhiên phản ánh thứ tự commit nếu transaction có thể hoàn tất lệch nhau.

Vì vậy hợp đồng anchored cần nói rõ **giả định về khóa** và không cam kết “đúng mọi bản ghi có tại thời điểm trang 1”. Việc xóa hoặc cập nhật thuộc tính lọc của bản ghi cũng có thể khiến nó biến mất, dù anchor không đổi.

### 8.3. Snapshot: cố định thành viên và trạng thái theo một phiên bản

Nếu nghiệp vụ yêu cầu **đúng tập bản ghi và nội dung tại một thời điểm**, cần kiến trúc có khả năng tái dựng trạng thái đó. Một số cách:

1. **Materialized snapshot:** tạo một bản ghi snapshot gồm tập ID và, khi cần, cả giá trị của từng bản ghi tại thời điểm chốt; trả mã snapshot/cursor có thời hạn.
2. **Temporal/versioned data:** lưu lịch sử thay đổi (phiên bản có hiệu lực theo thời điểm hoặc revision), rồi truy vấn các trang theo cùng một phiên bản đã được xác định.
3. **Snapshot export/job:** tạo tệp kết quả ở một phiên bản nhất quán và để client tải theo chunk/trang. Phù hợp cho xuất báo cáo hoặc đối soát lớn.
4. **Snapshot chuyên biệt của kho dữ liệu/công cụ tìm kiếm:** nếu backend hỗ trợ point-in-time hoặc snapshot read có thời hạn, dùng theo đúng quy tắc, giới hạn và chi phí retention của nền tảng.

**Lưu danh sách ID thôi chưa chắc đủ:** nếu ID còn trong snapshot nhưng nội dung record đã đổi hoặc bị xóa, việc truy vấn bảng sống theo ID sẽ không trả lại đúng representation cũ. Đối với dữ liệu cần xóa theo pháp luật hoặc thu hồi quyền, không được dùng snapshot như cách vượt qua yêu cầu bảo mật; phải định nghĩa cách hủy snapshot, ẩn dữ liệu hoặc từ chối truy cập.

## 9. MVCC, transaction và vì sao giữ transaction xuyên HTTP pages thường không thực tế

Nhiều CSDL quan hệ sử dụng **Multi-Version Concurrency Control (MVCC)** để đọc các phiên bản dữ liệu nhất quán theo transaction hoặc câu lệnh, tùy isolation level. Điều này thường bị diễn giải quá mức thành “mọi trang đều nhất quán”.

- Ở cấu hình PostgreSQL thông dụng **READ COMMITTED**, mỗi lệnh SELECT có snapshot phù hợp tại lúc lệnh bắt đầu; lệnh SELECT của request sau có thể nhìn thấy giao dịch commit mới.
- Trong một transaction PostgreSQL **REPEATABLE READ**, các truy vấn trong transaction có thể thấy cùng một snapshot dữ liệu. Nhưng hai HTTP request độc lập **không tự tham gia cùng transaction đó**.
- Nếu giữ một transaction CSDL mở cho toàn bộ thời gian người dùng duyệt hàng chục trang, thời gian có thể kéo dài từ giây tới phút hoặc hàng giờ; nó tiêu tốn connection, giữ snapshot, cản trở thu hồi phiên bản cũ và khó chịu được client ngắt kết nối.
- Các tính năng exported snapshot hoặc point-in-time của từng hệ CSDL có quy tắc sống/chết và giữ tài nguyên riêng. Không nên giả định có thể đóng transaction rồi tái sử dụng một snapshot ID mãi mãi.

Một request GET hoàn thành **không đồng nghĩa client nhận được một phiên bản bất biến của toàn bộ collection**. Nếu cần snapshot xuyên nhiều request, hãy sử dụng cơ chế snapshot có vòng đời rõ ràng, lưu trữ và giới hạn TTL thay vì dựa vào transaction thông thường.

## 10. Thiết kế hợp đồng HTTP cho phân trang có cursor

Một API chọn keyset có thể hỗ trợ:

```http
GET /orders?status=OPEN&limit=2 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
```

Phản hồi:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {"id":"ord-51","createdAt":"2026-11-18T09:00:00Z"},
    {"id":"ord-50","createdAt":"2026-11-18T08:58:00Z"}
  ],
  "page": {
    "limit": 2,
    "hasNext": true,
    "nextCursor": "opaque-signed-token",
    "consistency": "live",
    "sort": ["createdAt:desc", "id:desc"]
  },
  "links": {
    "next": "/orders?status=OPEN&limit=2&cursor=opaque-signed-token"
  }
}
```

`"opaque-signed-token"` chỉ minh họa giá trị cursor; server phải thực sự phát hành token được mã hóa/đóng dấu theo hợp đồng, không dùng chuỗi cố định. `links.next` và `page.consistency` là trường **do API tự định nghĩa**. API có thể dùng header `Link: <...>; rel="next"` theo web linking, hoặc JSON links; hãy nhất quán và tài liệu hóa.

Một cursor sau trang cuối:

```json
{
  "items": [{"id":"ord-3"}],
  "page": {
    "limit": 2,
    "hasNext": false,
    "nextCursor": null,
    "consistency": "live"
  }
}
```

Đây vẫn là **200 OK**, kể cả khi `items` rỗng. Trong API collection bình thường không cần trả 404 chỉ vì bộ lọc không có kết quả; 404 phù hợp khi URI resource đích không tồn tại theo hợp đồng. Không dùng `206 Partial Content` chỉ vì đây là một trang thông thường; 206 dành cho cơ chế range request theo ý nghĩa HTTP.

### Những tham số nên công bố

| Tham số | Ý nghĩa | Quy tắc nên áp dụng |
| --- | --- | --- |
| `limit` | Số bản ghi tối đa mỗi trang | Có min/max, ví dụ 1–100; giới hạn chi phí |
| `cursor` | Điểm tiếp tục hoặc token phiên bản trang | Opaque; xác thực, kiểm tra hạn và ràng buộc tham số |
| `status`, `createdFrom`, ... | Bộ lọc | Giá trị chuẩn hóa, kiểm tra quyền và binding an toàn |
| `sort` | Thứ tự kết quả | Allowlist cột và chiều sắp xếp; cần tie-breaker duy nhất |
| `consistency` (nếu hỗ trợ) | Yêu cầu live/anchored/snapshot | Chỉ cung cấp mức được triển khai thật |

Không nên để client tự đoán `nextCursor` từ ID cuối nếu hợp đồng đã chọn token opaque. Nên dùng nguyên `links.next` hoặc `page.nextCursor` do server cấp.

### Vì sao không bắt buộc có totalCount/totalPages?

Tổng số bản ghi có thể đắt tiền khi filter rộng, thay đổi ngay sau khi tính và không có ý nghĩa “tổng trang còn lại” ổn định trong live pagination. Nếu UI cần tổng, có thể trả `totalCount` riêng, ghi rõ đó là số liệu **tại một thời điểm**, có thể gần đúng hoặc tính bất đồng bộ. Tránh đưa số tổng tức thời vào hợp đồng như một lời hứa toàn bộ lượt duyệt đã được đóng băng.

## 11. Thiết kế cursor an toàn và tái sử dụng được

Cursor nên là một **token opaque** chứa hoặc tham chiếu tới trạng thái cần thiết. Không xem Base64 là mã hóa bảo mật; nếu nhét tenant ID, email hoặc dữ liệu riêng tư trong token chỉ Base64, client vẫn có thể đọc.

Một payload logic trước khi được ký/mã hóa hoặc lưu server-side:

```json
{
  "v": 1,
  "mode": "live",
  "sort": "createdAt:desc,id:desc",
  "anchor": null,
  "last": {
    "createdAt": "2026-11-18T08:58:00Z",
    "id": "ord-50"
  },
  "filterHash": "hash-of-canonical-query",
  "scopeHash": "hash-of-authorized-scope",
  "limit": 2,
  "expiresAt": "2026-11-18T09:30:00Z"
}
```

Khi sử dụng:

1. **Ký và xác thực tính toàn vẹn** của token, ví dụ HMAC với khóa được quản lý an toàn; nếu chứa thông tin nhạy cảm thì mã hóa hoặc dùng mã tham chiếu server-side.
2. **Ràng buộc với filter, sort, limit và phạm vi truy cập**; client sửa filter nhưng giữ cursor cũ phải bị từ chối hoặc được yêu cầu bắt đầu lại theo hợp đồng.
3. **Kiểm tra hạn dùng và phiên bản token**; hỗ trợ xoay khóa và phiên bản định dạng.
4. **Tái xác thực và phân quyền ở mọi request**, không coi token là giấy phép truy cập dữ liệu.
5. **Chuẩn hóa bộ lọc trước khi tính fingerprint** để các biểu diễn tương đương không gây lỗi vô cớ; khóa sort không lấy trực tiếp từ input SQL chưa kiểm tra.
6. **Giới hạn tài nguyên:** độ dài token, số trang, giới hạn limit, thời gian tồn tại snapshot và mức sử dụng của một client.

Một cursor bị sửa chữ ký hoặc không parse được thường có thể trả **400 Bad Request** với mã lỗi như `pagination.invalid_cursor`. Cursor hết hạn có thể trả **400**, **410 Gone** hoặc một lỗi 4xx khác tùy tài nguyên/semantics của API; không có quy định HTTP chung bắt buộc mọi cursor hết hạn phải trả 410. Hãy công bố status và cách client **bắt đầu lại từ trang đầu**. Nếu snapshot đã được dọn dẹp, tuyệt đối không lặng lẽ chuyển từ snapshot sang live mà vẫn dùng token cũ.

### Khi bản ghi cuối của trang trước bị xóa

Đây là ưu điểm thực tế của cursor lưu **khóa sắp xếp**. Nếu B vừa bị xóa, cursor vẫn ghi `(createdAt_B, id_B)`; câu SELECT tiếp theo có thể lấy các bản ghi nhỏ hơn khóa đó. Không cần truy vấn lại B để tìm vị trí của nó. Cursor chỉ chứa ID rồi cố đọc B để tìm timestamp sẽ hỏng khi B đã bị xóa, trừ khi có cách khôi phục khóa.

## 12. SQL keyset trong PostgreSQL

Giả sử bảng:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_minor_units BIGINT NOT NULL
);

CREATE INDEX idx_orders_tenant_status_created_id
  ON orders (tenant_id, status, created_at DESC, id DESC);
```

Để trang đầu với `status=OPEN`:

```sql
SELECT id, created_at, status, total_minor_units
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
```

Với cursor của trang trước:

```sql
SELECT id, created_at, status, total_minor_units
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
```

Nếu chọn hợp đồng anchored, thêm điều kiện `(created_at,id) <= (:anchor_created_at,:anchor_id)` cho các trang sau; lấy anchor từ trang đầu và giữ nguyên qua cursor. Điều này giới hạn khóa nằm trước đầu lượt duyệt nhưng vẫn có những giới hạn đã giải thích ở mục 8.

### Vì sao lấy `limit + 1`?

Giả sử client yêu cầu `limit=20`. Server lấy tối đa 21 bản ghi:

- Trả **20** bản ghi đầu cho client.
- Nếu tìm được bản ghi thứ **21** thì `hasNext=true`.
- Cursor trỏ tới **bản ghi cuối cùng thực sự đã trả** (thứ 20), không phải bản ghi thứ 21.
- Nếu không có bản ghi thứ 21 thì `hasNext=false`.

Không dùng `rows.size() == limit` để kết luận chắc chắn còn trang nữa: khi còn đúng 20 hàng, đó là trang cuối. Cũng không cần dùng `COUNT(*)` để xác định `hasNext` trong trường hợp này.

### Những điều kiện làm keyset kém hiệu quả hoặc sai

- Thứ tự hoặc filter không khớp index; truy vấn vẫn phải sort/scan nhiều.
- Kết hợp nhiều sort direction, NULL hoặc collation mà không xây comparator đúng.
- Phân trang theo `updated_at` hoặc điểm xếp hạng có thể đổi, nhưng lại cam kết không lặp/không thiếu.
- Có join một-nhiều làm nhân đôi hàng, rồi đặt LIMIT trước khi gom về resource.
- CSDL không hỗ trợ tuple comparison tương ứng; cần biểu thức `OR`/`AND` đúng theo thứ tự.
- Khóa thời gian không duy nhất, thiếu ID tie-breaker.
- Phân quyền hoặc filter thay đổi nhưng token không được kiểm tra phạm vi.

## 13. Ví dụ triển khai Java/Spring: tách cursor khỏi truy vấn dữ liệu

Đây là phác thảo của một API Spring Boot dùng PostgreSQL. Mục đích là minh họa **đúng ranh giới trách nhiệm và cách lấy trang**; các class `CursorCodec`, `OrdersDao` và DTO cần được triển khai theo dự án. Không có SDK Spring nào tự bảo đảm snapshot chỉ vì sử dụng `Pageable`.

### 13.1. Các kiểu dữ liệu hợp đồng

```java
record SortKey(Instant createdAt, UUID id) {}

record PageCursor(
    int version,
    SortKey lastKey,
    SortKey anchorKey, // null cho live; dùng cho anchored
    String queryFingerprint,
    Instant expiresAt
) {}

record OrderDto(UUID id, Instant createdAt, String status) {}

record PageResult<T>(
    List<T> items,
    String nextCursor,
    boolean hasNext,
    String consistency
) {}
```

Mỗi trường trong `PageCursor` mang thông tin logic, **không phải** JSON để client tự xây. `CursorCodec` phải xác thực chữ ký/token và từ chối phiên bản, filter/scope hoặc hạn dùng không hợp lệ.

### 13.2. Lấy trang sau khi kiểm tra cursor

```java
// Java 17+ / Spring; đoạn code minh họa, thiếu import và wiring thực tế.
@Service
class OrderQueryService {
    private final OrdersDao dao;
    private final CursorCodec cursorCodec;

    OrderQueryService(OrdersDao dao, CursorCodec cursorCodec) {
        this.dao = dao;
        this.cursorCodec = cursorCodec;
    }

    PageResult<OrderDto> list(
        UUID authorizedTenantId,
        String status,
        int requestedLimit,
        String cursorToken
    ) {
        int limit = Math.max(1, Math.min(requestedLimit, 100));
        String fingerprint = canonicalFingerprint(
            authorizedTenantId, status, limit, "createdAt:desc,id:desc"
        );

        PageCursor cursor = (cursorToken == null)
            ? null
            : cursorCodec.decodeAndVerify(cursorToken, fingerprint);

        // DAO luôn thêm điều kiện tenant/status từ server;
        // không lấy tenantId làm quyền truy cập chỉ vì cursor khai báo.
        List<OrderDto> fetched = dao.findAfter(
            authorizedTenantId,
            status,
            cursor == null ? null : cursor.lastKey(),
            limit + 1
        );

        boolean hasNext = fetched.size() > limit;
        List<OrderDto> items = fetched.subList(
            0, Math.min(fetched.size(), limit)
        );

        String next = null;
        if (hasNext && !items.isEmpty()) {
            OrderDto last = items.get(items.size() - 1);
            PageCursor nextState = new PageCursor(
                1,
                new SortKey(last.createdAt(), last.id()),
                null, // Chế độ live trong ví dụ
                fingerprint,
                Instant.now().plus(Duration.ofMinutes(20))
            );
            next = cursorCodec.encodeAndSign(nextState);
        }
        return new PageResult<>(items, next, hasNext, "live");
    }

    private String canonicalFingerprint(
        UUID tenant, String status, int limit, String sort
    ) {
        // Được triển khai bằng canonical serialization + hash an toàn.
        throw new UnsupportedOperationException("Minh họa hợp đồng");
    }
}
```

**Chú ý:** `canonicalFingerprint` phía trên là stub để làm rõ trách nhiệm, không phải code hoàn chỉnh để chạy trực tiếp. Production phải triển khai canonicalization, xác thực giá trị `status`, xử lý cursor lỗi thành Problem Details, lấy tenant từ security context và giới hạn độ dài token. Nếu không có bản ghi sau cuối trang, `nextCursor=null`. Khi limit bị thay đổi giữa request, hợp đồng có thể từ chối dùng cursor cũ; ví dụ đã ràng buộc limit vào fingerprint.

### 13.3. DAO truy vấn theo khóa

```java
// Phác thảo điều kiện phân trang, không bao gồm mapping RowMapper.
List<OrderDto> findAfter(UUID tenantId, String status,
                         SortKey after, int fetchSize) {
    String sql = """
        SELECT id, created_at, status
        FROM orders
        WHERE tenant_id = :tenantId
          AND status = :status
        """ +
        (after == null ? "" :
            " AND (created_at, id) < (:afterCreatedAt, :afterId)") +
        """
        ORDER BY created_at DESC, id DESC
        LIMIT :fetchSize
        """;

    // Dùng NamedParameterJdbcTemplate và bind parameter có kiểu.
    // Chỉ nối fragment SQL cố định của server, không nối input tự do.
    return executeQueryWithBoundParameters(sql, tenantId, status,
                                           after, fetchSize);
}
```

Phương thức `executeQueryWithBoundParameters` là helper giả định. Mã làm rõ rằng các tham số tenant/status/after/limit phải được **bind**; sort direction được **allowlist** chứ không ghép trực tiếp từ query string. Nếu dùng Spring Data JPA, có thể triển khai truy vấn keyset bằng query/repository tương ứng; `PageRequest.of(page, size)` mặc định biểu diễn pagination kiểu trang/offset và không tự chuyển thành keyset.

### 13.4. Controller và HTTP response

```java
// Tham chiếu service từ security context và map ra HTTP response.
@GetMapping("/orders")
ResponseEntity<PageResult<OrderDto>> listOrders(
    @RequestParam String status,
    @RequestParam(defaultValue = "20") int limit,
    @RequestParam(required = false) String cursor
) {
    UUID tenantId = currentAuthorizedTenantId();
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(orderQueryService.list(tenantId, status, limit, cursor));
}
```

Đoạn trên là ví dụ cấu trúc, chưa bao gồm imports, cấu hình authentication, validation và error mapping. Trong ứng dụng thật, quyền truy cập theo **từng đơn hàng** có thể phức tạp hơn tenant filtering; DAO/policy phải thực thi cả quy tắc phân quyền phù hợp trước khi trả dữ liệu.

## 14. Lỗi và hành vi client khi cursor không còn dùng được

Một API phân trang cần hợp đồng lỗi rõ ràng:

| Tình huống | Status gợi ý | Mã lỗi máy hiểu | Hành vi client |
| --- | --- | --- | --- |
| `limit` ngoài phạm vi hoặc sort không hỗ trợ | 400 | `pagination.invalid_parameter` | Sửa request |
| Cursor sai định dạng hoặc chữ ký không hợp lệ | 400 | `pagination.invalid_cursor` | Bắt đầu lại từ trang đầu |
| Cursor thuộc filter/sort khác | 400 | `pagination.cursor_query_mismatch` | Không tự ghép token vào truy vấn mới |
| Cursor hết hạn | 400 hoặc 410 theo hợp đồng | `pagination.cursor_expired` | Bắt đầu lượt duyệt mới |
| Snapshot được yêu cầu nhưng đã dọn dẹp | 410 hoặc status được quy định | `pagination.snapshot_unavailable` | Khởi tạo snapshot mới, xử lý khả năng thay đổi dữ liệu |
| Client không có quyền xem collection | 403 hoặc 404 theo chính sách | `auth.access_denied` | Không làm lộ dữ liệu |
| Hệ thống lưu snapshot không khả dụng | 503 khi phù hợp | `service.temporarily_unavailable` | Retry có giới hạn nếu an toàn |

Phản hồi minh họa khi cursor không hợp lệ:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/pagination/invalid-cursor",
  "title": "Không thể tiếp tục danh sách",
  "status": 400,
  "detail": "Trang tiếp theo không còn hợp lệ. Vui lòng tải lại từ đầu.",
  "code": "pagination.invalid_cursor"
}
```

Đừng trả nội dung cursor đã giải mã, khóa ký, SQL hoặc danh tính nhạy cảm trong response. `code` là extension riêng của API; `type`, `title` và các thuộc tính chuẩn tuân theo RFC 9457. Nếu yêu cầu bắt đầu lại tốn kém, có thể cung cấp hành động tái tạo snapshot/exports theo hợp đồng.

## 15. Cache, ETag và sự nhất quán của collection

Trong REST, GET có thể được cache theo các quy tắc HTTP. Nhưng **một trang GET có ETag không đồng nghĩa mọi trang thuộc một snapshot**:

- ETag dùng để xác nhận biểu diễn của **một response/URI** theo cơ chế HTTP conditional request; nó không tự khóa dữ liệu của các URI trang khác.
- HTTP `304 Not Modified` giúp giảm băng thông khi representation chưa đổi theo validator của trang tương ứng, **không bảo đảm** trang kế tiếp là ảnh chụp cùng thời điểm.
- Nếu response phụ thuộc vào người dùng, tenant, quyền hoặc ngôn ngữ, cache cần phân vùng/chính sách thích hợp để tránh lộ dữ liệu.
- Ở collection thay đổi thường xuyên, cache TTL có thể khiến trang 1 cũ và trang 2 mới bị trộn; mô tả rõ dữ liệu live và khi nào client cần refresh.
- Cursor chứa token cá nhân hoặc snapshot ID không được đưa vào shared cache key một cách thiếu kiểm soát; áp dụng `private`/`no-store` nếu cần.

Nếu cần “cả lượt đọc giữ nguyên cùng một phiên bản”, phải gắn các trang với **cơ chế snapshot thực sự**. Chỉ thêm trường `snapshotTime` ở response mà không có khả năng truy vấn lịch sử **không tạo** tính nhất quán snapshot.

## 16. Kiểm thử thêm/xóa giữa các request

Kiểm thử phân trang trong môi trường chỉ có fixture tĩnh sẽ bỏ qua chính lỗi cần phát hiện. Hãy làm hai request HTTP riêng biệt và **thực hiện thay đổi CSDL ở giữa**. Với PostgreSQL có thể sử dụng Testcontainers hoặc một DB test có tính năng/sắp xếp giống production.

### Ma trận kiểm thử

| Kịch bản | OFFSET/LIMIT dự kiến | Keyset với khóa bất biến | Cần assert |
| --- | --- | --- | --- |
| Không thay đổi dữ liệu | Duyệt tuần tự | Duyệt tuần tự | Từng item xuất hiện đúng một lần |
| Insert X trước khóa cuối trang 1 | Có thể trùng item | Không lặp item vì dịch chuyển trước cursor | ID B không được lặp ở keyset |
| Delete A trước khóa cuối trang 1 | Có thể bỏ C | C vẫn có thể xuất hiện ở trang sau | C được trả trong keyset |
| Delete chính item B cuối trang 1 | OFFSET dịch vị trí | Cursor giữ khóa B nên vẫn tiếp tục | Không cần truy vấn B còn tồn tại |
| Insert Y có khóa sau B | Trang 2 thay đổi | **Y có thể xuất hiện** | Không khẳng định cursor là snapshot |
| Hai item trùng timestamp | Có thể thứ tự bất định | Tie-breaker ID tránh bỏ một item | Phủ trường hợp sort key bằng nhau |
| Update trường sort của item đã xem | Dễ lặp/thiếu | **Cũng có thể lặp/thiếu** | Tài liệu hóa giới hạn hoặc dùng snapshot |
| Update `status` làm item rời filter | Tập kết quả biến động | Tập kết quả vẫn biến động | Không hứa trả đủ item của lúc bắt đầu |
| Filter/tenant thay đổi giữa hai trang | Sai phạm vi nếu xử lý lỏng | Cursor phải bị từ chối nếu mismatch | Không lộ dữ liệu khác tenant |
| Cursor bị chỉnh sửa hoặc hết hạn | Không áp dụng | Trả lỗi theo contract | Không có SQL injection/token bypass |
| Một trang có đúng `limit` item và hết dữ liệu | Cần kiểm tra thêm | `limit+1` cho biết không còn trang | `hasNext=false` |
| Một trang rỗng | Trả mảng rỗng | Trả mảng rỗng | 200 và cursor kết thúc đúng |

### Mẫu integration test (JUnit-style pseudocode)

```java
@Test
void deletingAnEarlierRowDoesNotSkipNextKeysetItem() {
    // Dữ liệu cố định: A > B > C > D > E theo createdAt, id.
    seedOrderedOrders("A", "B", "C", "D", "E");

    Page first = httpGetOrders("limit=2");
    assertIds(first.items(), "A", "B");
    String next = first.nextCursor();

    deleteOrder("A"); // thay đổi xảy ra giữa hai HTTP requests

    Page second = httpGetOrdersWithCursor(next);
    assertIds(second.items(), "C", "D");
}

@Test
void insertionBeforeCursorDoesNotRepeatPreviousItem() {
    seedOrderedOrders("A", "B", "C", "D", "E");
    Page first = httpGetOrders("limit=2");
    assertIds(first.items(), "A", "B");

    insertOrderBetween("A", "B", "X"); // X đứng trước B

    Page second = httpGetOrdersWithCursor(first.nextCursor());
    assertIds(second.items(), "C", "D");
}

@Test
void insertionAfterCursorCanAppearInLiveMode() {
    seedOrderedOrders("A", "B", "C", "D", "E");
    Page first = httpGetOrders("limit=2");

    insertOrderBetween("B", "C", "Y"); // Y đứng sau cursor B

    Page second = httpGetOrdersWithCursor(first.nextCursor());
    assertIds(second.items(), "Y", "C");
}
```

Đây là **pseudocode**, các helper `seedOrderedOrders`, `httpGetOrders`, `deleteOrder` và `insertOrderBetween` cần được hiện thực trong dự án. Dữ liệu được seed theo khóa có thứ tự xác định; dùng transaction độc lập/commit trước GET tiếp theo. Test không phụ thuộc `Thread.sleep()` hoặc thời gian máy. Riêng ca insert vào vị trí mong muốn phải tạo `createdAt`/ID phù hợp để thứ tự kiểm thử thật sự đúng.

### Kiểm thử snapshot cần mạnh hơn

Nếu API tuyên bố snapshot, cần assert cả:

1. Bản ghi **được thêm sau khi chốt snapshot** không xuất hiện.
2. Bản ghi **có mặt tại lúc chốt**, nhưng bị xóa sau đó, vẫn hiện theo biểu diễn snapshot nếu chính sách dữ liệu cho phép.
3. Các trường của bản ghi đã cập nhật sau đó không tự đổi trong snapshot cũ.
4. Cursor của snapshot hết hạn/hủy phải báo lỗi chính xác; không âm thầm trả live data.
5. Tenant/authorization được thực thi tại mỗi lần đọc snapshot; không thể dùng snapshot để vượt quyền hoặc yêu cầu xóa dữ liệu.

Một snapshot chỉ cố định ID nhưng không cố định giá trị **sẽ không qua** bài kiểm thử 3. Cần định nghĩa rõ snapshot bảo đảm thành viên, nội dung hay cả hai.

## 17. Chọn phương án theo nhu cầu và chi phí

| Bài toán | Phương án ưu tiên | Lý do | Điều cần chấp nhận/giải quyết |
| --- | --- | --- | --- |
| Danh sách sản phẩm tương tác, thay đổi liên tục | Keyset **live** với khóa sort ổn định | Dễ cuộn tiếp, hiệu quả trên tập lớn | Dữ liệu mới có thể xuất hiện/bị bỏ qua trong lượt duyệt |
| Bảng quản trị cần nhảy đến trang số 50 | OFFSET cho nhảy trang hoặc thiết kế tìm kiếm riêng | Truy cập ngẫu nhiên theo số trang thuận tiện | Vị trí có thể đổi; OFFSET sâu thường đắt |
| Feed sự kiện append-only, tạo theo khóa ổn định | Keyset + anchor nếu mô hình khóa cho phép | Hạn chế thay đổi ở đầu lượt duyệt | Backfill và commit trễ vẫn cần xem xét |
| Xuất toàn bộ đơn tại ngày chốt | Snapshot/job export với version rõ | Cần tập dữ liệu và giá trị nhất quán | Chi phí snapshot, lưu lịch sử, thời gian tạo |
| Đối soát giao dịch | Snapshot/version hoặc pipeline có watermark đã xác minh | Không được mất/đếm trùng giao dịch ở mốc chốt | Cần cơ chế source-of-truth, kiểm tra completeness |
| Tìm kiếm được xếp hạng lại thường xuyên | Cơ chế point-in-time của search backend nếu có | Rank đổi có thể làm cursor thuần túy mất ổn định | TTL, dung lượng index, độ trễ, quyền truy cập |

OFFSET phù hợp với dữ liệu nhỏ, ít thay đổi hoặc UI chấp nhận trang biến động và cần nhảy tới số trang. Keyset thường hiệu quả hơn khi đọc nối tiếp tập lớn có index phù hợp. Snapshot đắt hơn nhưng cần thiết khi hợp đồng đòi **đúng dữ liệu tại một phiên bản**.

### Các câu hỏi trước khi thiết kế

- Người dùng chỉ đang cuộn để **khám phá** hay đang làm việc cần **không bỏ sót**?
- Trường sort có thể thay đổi, có NULL, có trường hợp nhiều bản ghi bằng nhau không?
- Insert mới có thể mang khóa cũ (backfill, xử lý chậm, nhập dữ liệu lịch sử) không?
- Có cần số trang, tổng chính xác hoặc nhảy đến trang tùy ý không?
- Tập dữ liệu và độ trễ cho phép đủ để lưu snapshot bao lâu?
- Nếu quyền bị thu hồi giữa các trang, client có còn được xem bản ghi đã cấp trước không?
- Có yêu cầu audit/khôi phục, giới hạn chi phí cache/index và số request của một lượt duyệt không?

## 18. Bài thực hành: thiết kế API duyệt lịch sử giao dịch

Một hệ thống tài chính nội bộ cung cấp `GET /transactions` cho người quản trị được phân quyền. Nguồn dữ liệu ban đầu gồm:

```text
Giao dịch  Thời điểm tạo      Số tiền
T5        11:00             +100
T4        10:00              -40
T3        09:00             +200
T2        08:00              -30
T1        07:00              -10
```

API trả hai bản ghi/trang, sort theo `createdAt DESC, id DESC`. Sau khi client nhận `T5, T4`:

- Nhân viên khác tạo `T6` lúc 10:30.
- Giao dịch `T5` bị ẩn khỏi phạm vi truy vấn hiện tại theo chính sách nghiệp vụ.
- Một bản ghi lịch sử `T0` được nhập lại với `createdAt=08:30`.

### Nhiệm vụ A — Mô phỏng OFFSET và keyset

1. Viết danh sách hiện tại sau từng biến cố; tính nội dung `OFFSET 2`.
2. Tính nội dung keyset khi cursor đang giữ khóa của `T4`.
3. Giải thích vì sao xóa/ẩn phần tử trước cursor không làm keyset bỏ qua một vị trí.
4. Xác định liệu `T0` (dữ liệu nhập muộn) có xuất hiện trong trang kế tiếp khi dùng keyset live hoặc anchored không.

**Gợi ý:** `T6` lúc 10:30 đứng trước T4 nên keyset tiếp tục sau T4 sẽ không trả T6; T0 lúc 08:30 đứng sau T4 nên có thể xuất hiện. Một anchor lấy từ T5 vẫn không loại được T0. Nếu T5 bị ẩn, tập kết quả của OFFSET bị dịch vị trí.

### Nhiệm vụ B — Xác định hợp đồng

Thiết kế hai chế độ:

| Chế độ | Mục tiêu | Cách thực hiện gợi ý |
| --- | --- | --- |
| `live` | Hiển thị lịch sử mới nhất cho giao diện | Cursor keyset; chấp nhận dữ liệu thay đổi và cho refresh |
| `export-snapshot` | Xuất tập giao dịch tại một thời điểm chốt để đối soát | Tạo job/snapshot phiên bản; trả snapshot ID và cơ chế tải có hạn |

Viết rõ chế độ nào bảo đảm thành viên, chế độ nào bảo đảm cả giá trị giao dịch và cách xử lý bản ghi bị xóa/thu hồi quyền.

### Nhiệm vụ C — Thiết kế cursor và index

Đề xuất payload cursor có `lastKey`, sort, filter fingerprint, tenant/scope binding, expiry. Chọn index phù hợp với truy vấn:

```sql
CREATE INDEX idx_tx_tenant_created_id
  ON transactions (tenant_id, created_at DESC, id DESC);
```

Lập trình SQL dùng `LIMIT :limit_plus_one` và `(created_at,id) < (:last_created_at,:last_id)`. Nếu có filter trạng thái hoặc ngày bắt đầu, giải thích tác động tới index và cách không để cursor được dùng sai bộ lọc.

### Nhiệm vụ D — Kiểm thử

Viết integration test cho thêm mới trước/sau cursor, xóa bản ghi đầu, xóa đúng bản ghi cuối trang trước, hai timestamp bằng nhau, filter thay đổi, cursor hết hạn và điều kiện khách hàng bị đổi quyền. Với chế độ snapshot, kiểm chứng tập và giá trị tại cùng mốc chốt; đưa test đối soát số giao dịch và tổng số tiền.

### Nhiệm vụ E — Phân tích rủi ro

Giả sử yêu cầu “mọi giao dịch tại thời điểm mở báo cáo đều phải được xuất đủ đúng một lần”. Nêu vì sao **chỉ thay OFFSET bằng cursor chưa đủ**; đề xuất snapshot hoặc job export có watermark và xác nhận completeness. Trình bày chi phí lưu snapshot, thời gian xuất, khả năng xử lý dữ liệu bị xóa và cách giới hạn quyền truy cập.

### Tiêu chí đánh giá (100 điểm)

| Nội dung | Điểm |
| --- | ---: |
| Mô phỏng đúng lỗi trùng/bỏ sót của OFFSET | 20 |
| Keyset, tie-breaker, SQL và index chính xác | 20 |
| Phân biệt live, anchored, snapshot và giới hạn | 25 |
| Hợp đồng HTTP/cursor, bảo mật và lỗi | 15 |
| Kiểm thử dữ liệu thay đổi và quyền truy cập | 15 |
| Đánh đổi hiệu năng, chi phí và mục đích nghiệp vụ | 5 |

## 19. Những sai lầm cần tránh

1. **Phân trang không có `ORDER BY`:** thứ tự không được bảo đảm, trang biến động ngay cả khi ít thay đổi.
2. **Chỉ dùng timestamp làm cursor:** nhiều bản ghi cùng timestamp có thể bị bỏ sót.
3. **Cho rằng cursor là snapshot:** item mới có khóa nằm sau cursor vẫn có thể xuất hiện.
4. **Cho rằng anchor thời gian tạo bảo đảm snapshot:** backfill, commit muộn, update/delete phá giả định.
5. **Sắp xếp theo trường thay đổi nhưng hứa không trùng/không thiếu:** item có thể di chuyển qua ranh giới cursor.
6. **Giữ transaction DB mở trong suốt thời gian người dùng cuộn:** kéo dài retention và sử dụng connection.
7. **Đưa token Base64 chứa thông tin nhạy cảm và coi là bí mật:** Base64 có thể giải mã; cần ký và mã hóa hoặc dùng server-side token.
8. **Tin `tenantId` trong cursor mà bỏ authorization:** cursor không thay thế kiểm tra quyền.
9. **Cho client đổi filter khi đang dùng cursor cũ:** keyset trở nên không có ý nghĩa nhất quán.
10. **Bắt `COUNT(*)` trong mọi request để tính totalPages:** vừa tốn tài nguyên vừa tạo kỳ vọng số trang cố định.
11. **Đổi sang live khi snapshot hết hạn mà không báo:** làm mất bảo đảm mà client phụ thuộc.
12. **Test chỉ với dữ liệu tĩnh:** không phát hiện lỗi insert/delete giữa hai request.
13. **Dùng `206 Partial Content` cho mọi response phân trang:** không đúng cơ chế HTTP Range.
14. **Chỉ cố định ID của snapshot nhưng không cố định nội dung:** giá trị bản ghi có thể đổi trước khi trang sau được lấy.

## 20. Câu hỏi tự kiểm tra

1. Với danh sách `A,B,C,D,E`, page size 2, client đã nhận `A,B`: thêm `X` trước B khiến OFFSET 2 trả gì? Vì sao?
2. Nếu xóa A trước khi gọi OFFSET 2, phần tử nào có thể bị bỏ sót?
3. Cursor dùng khóa của phần tử cuối trang trước khác OFFSET ở điểm nào?
4. Nếu phần tử cuối trang trước bị xóa, cursor keyset cần lưu những gì để tiếp tục?
5. Vì sao cần `ORDER BY created_at DESC, id DESC` thay vì chỉ `created_at DESC`?
6. Thêm bản ghi Y có khóa nhỏ hơn cursor B sẽ ảnh hưởng thế nào tới live keyset?
7. Với sort theo `updated_at DESC`, vì sao keyset vẫn có thể lặp/bỏ item?
8. Anchor từ bản ghi đầu có ngăn được dữ liệu lịch sử được nhập muộn với `createdAt` cũ không?
9. Vì sao mức isolation `REPEATABLE READ` của một request không tạo snapshot cho nhiều request HTTP độc lập?
10. Snapshot chỉ chứa danh sách ID có bảo đảm giá trị bản ghi giữ nguyên không? Cần cơ chế gì thêm?
11. `limit + 1` giúp xác định `hasNext` mà không cần `COUNT(*)` như thế nào?
12. Nếu một client đổi `status=OPEN` thành `status=CLOSED` nhưng vẫn gửi cursor cũ, server nên phản hồi thế nào?
13. Cursor được ký có thể thay thế kiểm tra quyền truy cập theo tenant không?
14. ETag của một trang có bảo đảm các trang sau thuộc cùng snapshot không?
15. Với nghiệp vụ xuất sổ giao dịch không được thiếu hoặc lặp, bạn chọn live, anchored hay snapshot? Bằng chứng nào chứng minh tính đầy đủ?

**Điểm cần ghi nhớ:** mỗi trang của một REST collection có thể được tính tại một thời điểm khác nhau. **OFFSET** dễ trùng hoặc bỏ sót khi phần tử trước vị trí hiện tại được thêm/xóa; **keyset/cursor** tiếp tục từ khóa ổn định nên giảm lỗi dịch chuyển vị trí, nhưng **không tự bảo đảm snapshot** trước insert có khóa cũ, update, delete hoặc thay đổi quyền/bộ lọc. Muốn duyệt nhất quán, hãy quy định rõ mức bảo đảm cần thiết, dùng thứ tự toàn phần, bảo vệ cursor, kiểm thử các thay đổi giữa hai request và chỉ hứa snapshot khi hệ thống thực sự có thể tái dựng đúng tập dữ liệu cùng phiên bản.
