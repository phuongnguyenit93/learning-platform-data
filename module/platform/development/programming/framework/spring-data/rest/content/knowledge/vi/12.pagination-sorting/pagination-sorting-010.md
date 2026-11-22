# Thứ tự ổn định, trang vượt phạm vi và dữ liệu thay đổi giữa các lần đọc

Phân trang giúp client đọc một tập kết quả lớn thành nhiều phần nhỏ. Tuy nhiên, việc gửi `page` và `size` không tự bảo đảm rằng các trang luôn ổn định khi dữ liệu thay đổi. Nếu thứ tự sắp xếp không xác định, bản ghi có thể xuất hiện lặp hoặc bị bỏ qua ngay cả khi dữ liệu không đổi. Nếu có insert hoặc delete giữa hai request, phân trang theo offset còn có thể dịch chuyển ranh giới trang. Client cũng cần xử lý trường hợp yêu cầu một trang không còn nằm trong phạm vi kết quả.

## 1. Vì sao thứ tự ổn định quan trọng?

Một truy vấn phân trang cần có thứ tự xác định để server biết bản ghi nào thuộc trang 0, trang 1 và các trang tiếp theo. Nếu không có `ORDER BY` hoặc `Sort` rõ ràng, database không bảo đảm thứ tự hàng trả về. Thứ tự có thể khác giữa các lần chạy, do execution plan, index, dữ liệu hoặc cấu hình database thay đổi.

Ngay cả khi có sort, nếu thuộc tính được sắp xếp có giá trị trùng nhau thì thứ tự giữa các bản ghi cùng giá trị vẫn chưa được xác định đầy đủ.

Ví dụ có các order sau:

| id | createdAt |
|---:|---|
| 101 | 2026-05-10T09:00:00Z |
| 102 | 2026-05-10T09:00:00Z |
| 103 | 2026-05-10T08:30:00Z |
| 104 | 2026-05-10T08:00:00Z |

Nếu chỉ sắp xếp theo `createdAt,desc`, hai order 101 và 102 có cùng giá trị. Database có thể trả chúng theo thứ tự khác nhau giữa hai truy vấn. Khi page size nhỏ, một bản ghi có thể đổi vị trí qua ranh giới trang.

Để tạo thứ tự ổn định hơn, thêm một thuộc tính duy nhất làm tiêu chí phụ:

```http
GET /orders?page=0&size=2&sort=createdAt,desc&sort=id,asc
Accept: application/hal+json
```

Thứ tự được xác định lần lượt bởi `createdAt` giảm dần rồi `id` tăng dần. Vì `id` là duy nhất, mỗi order có vị trí xác định trong kết quả tại thời điểm truy vấn.

## 2. Thứ tự ổn định trong Spring Data

Spring Data REST nhận các tham số sort và chuyển chúng thành `Sort` hoặc một phần của `Pageable`. Có thể truyền nhiều tham số `sort` để tạo thứ tự nhiều cấp:

```http
GET /orders?sort=status,asc&sort=createdAt,desc&sort=id,asc&page=0&size=20
```

Tương đương ý tưởng:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);
```

Các tên sort phải là property path mà repository có thể sắp xếp. Không dùng tên cột SQL hoặc tên hiển thị trong JSON nếu chúng không trùng với thuộc tính domain được hỗ trợ.

Khi thiết kế API, nên:

- Chọn một sort mặc định có thứ tự xác định, thường kết thúc bằng khóa duy nhất.
- Giới hạn các thuộc tính sort được phép để tránh truy vấn tốn kém hoặc sắp xếp theo field không phù hợp.
- Dùng cùng một thứ tự cho mọi request khi client đang duyệt một chuỗi trang.
- Giữ nguyên filter và sort khi theo link `next` hoặc tạo request trang kế tiếp.

Một sort có khóa duy nhất tạo thứ tự toàn phần cho tập dữ liệu tại thời điểm truy vấn. Nó giải quyết sự mơ hồ do các giá trị sort trùng nhau, nhưng không đóng băng dữ liệu giữa nhiều request.

## 3. Offset pagination hoạt động như thế nào?

Phân trang theo page/size thường được thực hiện bằng cách bỏ qua một số bản ghi rồi lấy số lượng tiếp theo. Với `page` bắt đầu từ 0:

`offset = page × size`

Ví dụ size bằng 20:

| page | offset | Khoảng vị trí |
|---:|---:|---|
| 0 | 0 | 1–20 |
| 1 | 20 | 21–40 |
| 2 | 40 | 41–60 |

Với Spring Data, `Pageable` mang thông tin page, size và sort để repository thực hiện truy vấn tương ứng. Offset pagination dễ dùng và phù hợp với giao diện có nút chuyển trang hoặc cần nhảy đến một trang cụ thể.

Tuy nhiên, offset mô tả vị trí trong kết quả hiện tại. Nếu tập kết quả thay đổi giữa các lần đọc, vị trí của các bản ghi cũng thay đổi. `page=1` không có nghĩa là “đọc tiếp sau bản ghi cuối cùng tôi đã nhận”; nó có nghĩa là “bỏ qua 20 bản ghi đầu theo trạng thái và thứ tự tại thời điểm request này được xử lý”.

## 4. Vì sao insert có thể làm lặp bản ghi?

Giả sử client đọc trang 0 với size 3, sắp xếp theo `createdAt,desc`:

<text>

</text>

Ban đầu thứ tự là:

```text
A, B, C | D, E, F | G, H, I
  page 0  |  page 1
```

Client đọc page 0 và nhận A, B, C. Trước khi client gọi page 1, một bản ghi mới X được thêm vào đầu danh sách:

```text
X, A, B | C, D, E | F, G, H, I
  page 0  |  page 1
```

Request page 1 bỏ qua ba phần tử đầu theo dữ liệu mới, vì vậy trả C, D, E. Client đã nhận C ở page 0 trước đó và giờ nhận lại C lần nữa.

Thứ tự có khóa phụ duy nhất vẫn không ngăn được tình huống này: thứ tự hiện tại hoàn toàn xác định, nhưng vị trí của bản ghi đã dịch chuyển vì X được thêm vào trước nó.

## 5. Vì sao delete có thể làm bỏ sót bản ghi?

Tình huống ngược lại xảy ra khi một bản ghi ở phía trước offset bị xóa.

Ban đầu:

```text
A, B, C | D, E, F | G, H, I
  page 0  |  page 1
```

Client đọc page 0, nhận A, B, C. Sau đó A bị xóa. Kết quả hiện tại:

```text
B, C, D | E, F, G | H, I
  page 0  |  page 1
```

Khi client yêu cầu page 1, server bỏ qua ba phần tử hiện tại là B, C, D và trả E, F, G. D chưa từng được client nhận, nhưng lại bị bỏ qua do offset dịch chuyển.

Các thay đổi thuộc tính sort cũng có thể tạo hiệu ứng tương tự: một bản ghi được cập nhật khiến nó chuyển từ phía sau lên phía trước hoặc ngược lại. Vì thế, dữ liệu thay đổi không chỉ là insert/delete mà còn có thể là update các field tham gia sort hoặc filter.

## 6. Trang vượt phạm vi và trang rỗng

Một trang vượt phạm vi xảy ra khi chỉ số `page` không còn trỏ đến phần kết quả hiện có. Ví dụ, truy vấn có 47 kết quả và size 20 thì có ba trang hợp lệ: 0, 1 và 2. Nếu client yêu cầu `page=3`, response thường có collection rỗng.

Các trường hợp thường gặp:

- Client gửi page lớn hơn hoặc bằng `totalPages`.
- Trang từng tồn tại nhưng các bản ghi bị xóa làm tổng số trang giảm.
- Filter được thay đổi khiến số kết quả giảm, trong khi client vẫn giữ page cũ.
- Một trang có thể rỗng vì không có kết quả phù hợp, không nhất thiết là endpoint bị lỗi.

Với `Page<T>`, metadata có thể cho biết `number` được yêu cầu, `size`, `totalElements` và `totalPages`. Nếu totalPages bằng 0 thì tập kết quả không có trang nào. Nếu page vượt phạm vi, client cần đọc metadata và nội dung thực tế để quyết định cách hiển thị.

Không nên giả định Spring Data REST luôn tự chuyển page vượt phạm vi về trang cuối. Hành vi cụ thể phụ thuộc cách endpoint tạo Page và framework version; client nên xử lý response theo contract thay vì dựa vào việc server tự điều chỉnh.

## 7. Chọn cách xử lý trang vượt phạm vi

API và client cần thống nhất cách phản ứng khi page không còn hợp lệ. Một số lựa chọn:

| Cách xử lý | Hành vi | Khi phù hợp |
|---|---|---|
| Trả trang rỗng cùng metadata | Giữ page được yêu cầu; content rỗng | API dùng semantics phân trang thông thường |
| Client quay về trang cuối | Tính lại từ totalPages rồi tải lại | Giao diện muốn giữ người dùng ở phần dữ liệu gần nhất |
| Client quay về trang đầu | Đặt page=0 và tải lại | Filter/sort vừa thay đổi hoặc không thể giữ vị trí |
| Server từ chối request | Trả lỗi theo API contract | Ứng dụng muốn page ngoài phạm vi là request không hợp lệ |

Ví dụ logic phía client:

```text
if (totalPages == 0) {
    showEmptyState();
} else if (requestedPage >= totalPages) {
    loadPage(totalPages - 1);
} else {
    renderCurrentPage();
}
```

Đây là pseudocode. Nếu client tự tải lại trang cuối, cần tránh vòng lặp khi dữ liệu tiếp tục thay đổi. Nên giới hạn số lần tự điều chỉnh và dùng metadata từ response mới nhất.

Nếu filter hoặc sort thay đổi, cách dễ hiểu nhất thường là quay về page 0. Trang 5 của một filter cũ không có ý nghĩa ổn định đối với filter mới.

## 8. Giảm ảnh hưởng của dữ liệu thay đổi giữa các request

Có nhiều mức giải pháp, tùy yêu cầu nhất quán và chi phí hệ thống.

### 8.1. Sort ổn định với khóa duy nhất

Luôn dùng sort xác định, chẳng hạn `createdAt,desc` và `id,asc`. Cách này ngăn database tùy ý đổi thứ tự giữa các bản ghi có cùng createdAt.

Giải pháp này cần có trong hầu hết API phân trang, nhưng chỉ giải quyết thứ tự không xác định. Nó không ngăn insert/delete làm dịch chuyển offset.

### 8.2. Snapshot hoặc transaction nhất quán

Nếu nghiệp vụ yêu cầu mọi trang phản ánh cùng một trạng thái dữ liệu, có thể cần snapshot nhất quán hoặc transaction với isolation phù hợp. Tuy nhiên, giữ một transaction mở xuyên suốt nhiều HTTP request thường không thực tế: transaction có thể kéo dài, giữ tài nguyên và gây áp lực lên connection pool hoặc database.

Một cách khác là tạo snapshot/export job ở server: server ghi nhận tập ID hoặc trạng thái dữ liệu tại một thời điểm, rồi client duyệt snapshot đó bằng token. Đây là thiết kế ứng dụng riêng, không tự động được cung cấp chỉ bằng tham số `page`.

### 8.3. Keyset/seek pagination

Keyset pagination dùng giá trị của bản ghi cuối cùng đã đọc làm mốc cho request tiếp theo, thay vì bỏ qua N hàng. Ví dụ sắp xếp `createdAt DESC, id ASC`. Sau khi đọc bản ghi cuối có `createdAt = T` và `id = 42`, truy vấn tiếp theo có thể lấy những bản ghi đứng sau mốc đó theo thứ tự:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at DESC, id ASC
LIMIT :size
```

Keyset tránh việc offset phải dịch qua các bản ghi mới được chèn ở đầu danh sách và thường hiệu quả hơn khi duyệt sâu trong tập dữ liệu lớn. Nó vẫn cần sort ổn định và các giá trị cursor phù hợp; bản ghi bị xóa hoặc thay đổi sort key vẫn có thể ảnh hưởng đến kết quả. Keyset cũng không thuận tiện cho việc nhảy thẳng đến một số trang bất kỳ.

Spring Data có hỗ trợ các abstraction scrolling/Window trong những phiên bản và loại query phù hợp, nhưng không phải mọi search method Spring Data REST đều tự động biến thành cursor endpoint. Để công bố cursor qua REST thường cần thiết kế endpoint và token theo contract ứng dụng.

## 9. HAL navigation links và cách client duyệt trang

Với representation HAL, client thường nhận các link như `self`, `next`, `prev`, `first` và `last`. Client nên theo các link server công bố để giữ filter, sort, page size và base path.

Ví dụ:

```json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=20&sort=createdAt,desc&sort=id,asc"
    },
    "prev": {
      "href": "/orders?page=0&size=20&sort=createdAt,desc&sort=id,asc"
    },
    "next": {
      "href": "/orders?page=2&size=20&sort=createdAt,desc&sort=id,asc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 47,
    "totalPages": 3,
    "number": 1
  }
}
```

Các link minh họa có thể vắng mặt ở trang đầu, trang cuối hoặc khi không có kết quả. Nếu không có `next`, client không nên tự giả định vẫn còn trang tiếp theo chỉ dựa vào page number. Nếu dữ liệu thay đổi, response mới có thể có metadata và navigation links khác response trước.

## 10. Checklist thiết kế API và client

1. Luôn định nghĩa sort rõ ràng; thêm khóa duy nhất làm tiêu chí cuối để tạo thứ tự toàn phần.
2. Giữ nguyên filter và sort trong suốt một lượt duyệt các trang.
3. Xử lý collection rỗng và page vượt phạm vi; không giả định server tự clamp về trang cuối.
4. Khi filter/sort thay đổi, đưa client về page 0.
5. Nhận thức rằng insert, delete hoặc update sort key có thể làm offset pagination lặp hoặc bỏ sót bản ghi.
6. Theo HAL navigation links thay vì tự ghép URL khi server công bố links.
7. Nếu cần snapshot nhất quán, cân nhắc snapshot token hoặc cơ chế export theo phiên.
8. Nếu cần duyệt dữ liệu lớn có thay đổi liên tục, cân nhắc keyset/cursor pagination thay cho offset.
9. Kiểm thử tình huống insert/delete giữa hai lần đọc, trang cuối bị thu hẹp và request page vượt phạm vi.

Sort ổn định là nền tảng để phân trang có thứ tự xác định; xử lý page vượt phạm vi giúp client phục hồi khi tập kết quả thay đổi; còn snapshot hoặc keyset pagination giải quyết những yêu cầu nhất quán cao hơn. Với Spring Data REST, client cần kết hợp metadata Page và HAL links với một chính sách rõ ràng cho dữ liệu biến động, thay vì xem page number là một con trỏ cố định vào tập dữ liệu.
