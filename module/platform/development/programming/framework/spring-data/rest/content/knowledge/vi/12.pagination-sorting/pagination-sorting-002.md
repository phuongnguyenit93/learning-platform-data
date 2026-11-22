# Tham số `page`, `size` và quy ước chỉ số trang bắt đầu từ 0

## Mục tiêu

Khi đọc xong bài này, bạn có thể:

- Gọi một collection endpoint của Spring Data REST bằng tham số `page` và `size`.
- Xác định trang đầu tiên, trang tiếp theo và trang cuối cùng theo quy ước đánh số từ 0.
- Đọc đúng thông tin phân trang trong response, đặc biệt là `page.number` và `page.totalPages`.
- Tránh lỗi lệch một trang khi kết nối giao diện người dùng với API.

## 1. Hai tham số có ý nghĩa gì?

Spring Data REST hỗ trợ phân trang cho tài nguyên dạng collection. Với cấu hình mặc định, client truyền thông tin phân trang qua query string:

- **`page`**: chỉ số của trang cần lấy. Đây là chỉ số **bắt đầu từ 0**.
- **`size`**: số phần tử tối đa mà client muốn nhận trong một trang.

Ví dụ:

~~~http
GET /people?page=0&size=20
~~~

Request trên yêu cầu trang đầu tiên của collection `people`, tối đa 20 phần tử.

Quy ước cần nhớ:

| Giá trị `page` | Trang được yêu cầu | Ý nghĩa |
|---:|---|---|
| `0` | Trang thứ nhất | Bắt đầu từ phần tử đầu tiên |
| `1` | Trang thứ hai | Bỏ qua trang đầu tiên |
| `2` | Trang thứ ba | Bỏ qua hai trang đầu tiên |
| `3` | Trang thứ tư | Bỏ qua ba trang đầu tiên |

Vì vậy, **`page=0` mới là trang đầu tiên**. Nếu gửi `page=1`, API trả về trang thứ hai, không phải trang đầu tiên.

`size` không phải tổng số bản ghi của collection. Nó chỉ là giới hạn số phần tử trong một lần trả về. Ví dụ, `size=10` nghĩa là mỗi trang có tối đa 10 phần tử; collection có 95 phần tử thì vẫn cần nhiều request để đọc hết.

## 2. Hiểu vị trí dữ liệu của từng trang

Có thể hình dung vị trí bắt đầu của một trang bằng công thức:

**Vị trí bắt đầu (offset) = `page × size`**

Ví dụ với `size=10`:

| Request | Offset | Các vị trí phần tử theo cách đếm từ 1 |
|---|---:|---|
| `page=0&size=10` | 0 | 1–10 |
| `page=1&size=10` | 10 | 11–20 |
| `page=2&size=10` | 20 | 21–30 |
| `page=3&size=10` | 30 | 31–40 |

Offset là vị trí bắt đầu tính từ 0 trong cách biểu diễn kỹ thuật. Client **không truyền offset vào tham số `page`**. Ví dụ, muốn lấy nhóm phần tử từ vị trí 21 đến 30 theo cách đếm thông thường, hãy gửi `page=2&size=10`, không gửi `page=20`.

## 3. Giá trị mặc định và giới hạn

Nếu client bỏ qua `page`, Spring Data thường hiểu là trang có chỉ số 0. Nếu bỏ qua `size`, server sử dụng kích thước trang mặc định đã cấu hình. Spring Data REST thường có page size mặc định là 20, nhưng ứng dụng có thể thay đổi giá trị này.

Server cũng có thể đặt giới hạn kích thước trang tối đa. Vì vậy:

- Nên gửi rõ `page` và `size` khi client cần kết quả có thể dự đoán.
- Dùng `page` là số nguyên không âm và `size` là số nguyên dương.
- Không mặc định rằng server chấp nhận mọi giá trị `size` mà client gửi.
- Khi cần biết giá trị thực tế, hãy đọc metadata phân trang trong response.

Tên tham số `page` và `size` là tên mặc định phổ biến của Spring Data REST. Ứng dụng có thể cấu hình tên tham số hoặc kích thước trang khác, nên client cần tuân theo hợp đồng API mà server công bố.

## 4. Đọc metadata phân trang trong response

Một response HAL của Spring Data REST thường có ba phần đáng chú ý:

- `_embedded`: chứa các phần tử của collection trong trang hiện tại.
- `_links`: chứa các liên kết điều hướng như `first`, `prev`, `self`, `next`, `last` khi phù hợp.
- `page`: chứa thông tin tổng quan về phân trang.

Ví dụ minh họa: collection có 12 người, mỗi trang lấy tối đa 5 người. Response của request `GET /people?page=1&size=5` có thể có cấu trúc như sau:

~~~json
{
  "_embedded": {
    "people": [
      { "name": "Person 6" },
      { "name": "Person 7" },
      { "name": "Person 8" },
      { "name": "Person 9" },
      { "name": "Person 10" }
    ]
  },
  "_links": {
    "first": { "href": "/people?page=0&size=5" },
    "prev": { "href": "/people?page=0&size=5" },
    "self": { "href": "/people?page=1&size=5" },
    "next": { "href": "/people?page=2&size=5" },
    "last": { "href": "/people?page=2&size=5" }
  },
  "page": {
    "size": 5,
    "totalElements": 12,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Ý nghĩa các trường trong `page`:

| Trường | Ý nghĩa |
|---|---|
| `size` | Kích thước trang được áp dụng |
| `totalElements` | Tổng số phần tử trong toàn bộ kết quả |
| `totalPages` | Tổng số trang |
| `number` | Chỉ số 0-based của trang hiện tại |

Trong ví dụ, `number=1` nghĩa là response đang ở **trang thứ hai**. `totalPages=3` nghĩa là có ba trang, với các chỉ số hợp lệ lần lượt là 0, 1 và 2. Không lấy `totalPages` làm chỉ số của trang cuối; chỉ số trang cuối là `totalPages - 1` khi có ít nhất một trang.

Trang cuối có thể chứa ít phần tử hơn `size`. Với 12 phần tử và `size=5`, ba trang lần lượt chứa 5, 5 và 2 phần tử. Điều đó không có nghĩa kích thước trang đã thay đổi.

## 5. Thử gọi API theo từng trang

Giả sử repository được expose tại endpoint `/people` và server cho phép lấy 5 phần tử mỗi trang:

~~~http
GET /people?page=0&size=5
GET /people?page=1&size=5
GET /people?page=2&size=5
~~~

Nếu tổng cộng có 12 phần tử:

- Request thứ nhất nhận tối đa 5 phần tử đầu tiên.
- Request thứ hai nhận tối đa 5 phần tử tiếp theo.
- Request thứ ba nhận 2 phần tử còn lại.

Bạn có thể thay đổi `size` mà không cần thay đổi quy ước của `page`. Ví dụ `page=0&size=10` lấy tối đa 10 phần tử đầu tiên; `page=1&size=10` lấy tối đa 10 phần tử tiếp theo.

Khi response cung cấp các liên kết điều hướng trong `_links`, nên ưu tiên sử dụng các liên kết đó. Chúng giúp client giữ đúng các tham số mà server đã áp dụng, bao gồm cả tham số sắp xếp hoặc lọc nếu API có sử dụng.

## 6. Kết nối với giao diện người dùng

Nhiều thư viện giao diện hiển thị số trang bắt đầu từ 1 để người dùng dễ hiểu, trong khi Spring Data dùng chỉ số bắt đầu từ 0. Khi tích hợp, cần chuyển đổi rõ ràng:

- Giao diện đang ở trang 1 → gửi `page=0`.
- Giao diện đang ở trang 2 → gửi `page=1`.
- Response có `page.number=1` → hiển thị trang 2 trên giao diện.

Có thể biểu diễn quy tắc chuyển đổi như sau:

~~~text
apiPage = uiPage - 1
uiPage  = apiPage + 1
~~~

Một số lưu ý khi quản lý trạng thái phân trang ở client:

1. Khởi tạo trang API ở chỉ số 0.
2. Giữ `page` và `size` trong trạng thái của màn hình để có thể tải lại đúng trang.
3. Khi người dùng đổi `size`, thường nên đưa `page` về 0. Trang đang chọn có thể không còn hợp lệ với kích thước mới.
4. Khi đổi bộ lọc làm tập kết quả nhỏ đi, nên kiểm tra lại metadata và đưa người dùng về trang hợp lệ nếu trang hiện tại vượt quá trang cuối.
5. Khi tự tạo URL, giữ lại các tham số sắp xếp và lọc cần thiết. Nếu API đã trả về `_links`, ưu tiên dùng các URL đó.

## 7. Các lỗi thường gặp

**Gửi `page=1` để lấy trang đầu tiên**

Đây là lỗi lệch một đơn vị phổ biến. Theo quy ước 0-based, `page=1` là trang thứ hai. Hãy bắt đầu bằng `page=0`.

**Nhầm `page` với offset**

Với `size=20`, trang thứ ba có `page=2`, không phải `page=40`. Offset được tính từ `page × size`; nó không phải giá trị cần gửi vào tham số `page`.

**Nhầm `totalPages` với chỉ số trang cuối**

Nếu `totalPages=3`, các trang có chỉ số 0, 1, 2. Trang cuối có chỉ số 2.

**Coi `size` là tổng số bản ghi**

`size=10` chỉ giới hạn số phần tử của một trang. Nó không yêu cầu server chỉ tìm 10 bản ghi trong toàn bộ collection.

**Coi `page.number` là số trang bắt đầu từ 1**

Trong metadata Spring Data, `number` cũng dùng chỉ số bắt đầu từ 0. Nếu dùng trực tiếp trên giao diện, hãy cộng 1 để hiển thị cho người dùng.

**Yêu cầu một trang nằm ngoài phạm vi**

Nếu client gửi chỉ số trang lớn hơn trang cuối, kết quả có thể rỗng. Hãy dựa vào `totalPages` và các liên kết điều hướng trong response để kiểm soát việc chuyển trang.

## 8. Bài tập tự kiểm tra

Một endpoint trả về tổng cộng 23 bản ghi. Client gửi `size=10`.

1. Request nào lấy 10 bản ghi đầu tiên?
2. Request nào lấy nhóm bản ghi từ 11 đến 20?
3. Chỉ số `page` của trang cuối là bao nhiêu?
4. `totalPages` bằng bao nhiêu?
5. Nếu giao diện đang hiển thị trang số 3, client cần gửi `page` bằng bao nhiêu?

**Đáp án:**

1. `page=0&size=10`.
2. `page=1&size=10`.
3. Chỉ số trang cuối là 2.
4. `totalPages=3`.
5. Gửi `page=2`, vì giao diện hiển thị từ 1 còn API đánh số từ 0.

## Ghi nhớ

- `page` là chỉ số trang, bắt đầu từ **0**.
- `size` là số phần tử tối đa trong một trang.
- Vị trí bắt đầu của trang được tính bằng `page × size`.
- `page.number` trong metadata cũng là chỉ số 0-based.
- `totalPages` là số lượng trang; chỉ số trang cuối là `totalPages - 1` khi kết quả có trang.
- Ưu tiên các liên kết điều hướng do Spring Data REST trả về để giữ đúng hợp đồng API.

Tham khảo: [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html).
