# Liên kết first, prev, next và last trong kết quả phân trang

## Bối cảnh

Khi Spring Data REST xuất bản một repository có hỗ trợ phân trang, request GET tới collection resource có thể trả về một trang dữ liệu thay vì toàn bộ bản ghi. Representation HAL không chỉ chứa các phần tử của trang hiện tại mà còn có các liên kết điều hướng để client chuyển tới trang đầu, trang trước, trang kế tiếp và trang cuối.

Bốn relation thường gặp là:

- `first`: trang đầu tiên.
- `prev`: trang ngay trước trang hiện tại.
- `next`: trang ngay sau trang hiện tại.
- `last`: trang cuối cùng.

Ví dụ, collection resource `/orders` có thể trả về các link:

    /orders?page=0&size=10
    /orders?page=1&size=10
    /orders?page=2&size=10

Client nên dùng `href` mà server cung cấp trong HAL để điều hướng. Những link này phản ánh cấu hình phân trang, sorting, base path và trạng thái dữ liệu mà server đang công bố.

## 1. Bật phân trang trên repository

Spring Data REST tự xuất bản các repository resource. Nếu repository hỗ trợ `PagingAndSortingRepository` hoặc một interface kế thừa khả năng paging/sorting như `JpaRepository`, collection resource có thể được truy vấn theo trang.

Ví dụ:

    @Entity
    public class Order {

        @Id
        @GeneratedValue
        private Long id;

        private String status;

        private Instant createdAt;

        // constructors, getters and setters
    }

    @RepositoryRestResource(path = "orders")
    public interface OrderRepository
            extends JpaRepository<Order, Long> {
    }

Với repository trên, collection resource có path:

    http://localhost:8080/orders

Request phân trang:

    GET /orders?page=0&size=10
    Accept: application/hal+json

Hai tham số chính:

| Tham số | Ý nghĩa |
| --- | --- |
| `page` | Chỉ số trang, bắt đầu từ 0 |
| `size` | Số phần tử tối đa được yêu cầu cho một trang |

Vì chỉ số trang bắt đầu từ 0, `page=0` là trang đầu tiên, `page=1` là trang thứ hai. `size=10` yêu cầu tối đa 10 phần tử trên một trang. Trang cuối có thể chứa ít phần tử hơn nếu tổng số bản ghi không chia hết cho kích thước trang.

## 2. Đọc cấu trúc HAL của một trang

Một response rút gọn có thể có dạng:

    {
      "_embedded": {
        "orders": [
          { "id": 41, "status": "PAID" },
          { "id": 42, "status": "NEW" }
        ]
      },
      "_links": {
        "first": {
          "href": "http://localhost:8080/orders?page=0&size=2"
        },
        "prev": {
          "href": "http://localhost:8080/orders?page=2&size=2"
        },
        "self": {
          "href": "http://localhost:8080/orders?page=3&size=2"
        },
        "next": {
          "href": "http://localhost:8080/orders?page=4&size=2"
        },
        "last": {
          "href": "http://localhost:8080/orders?page=6&size=2"
        }
      },
      "page": {
        "size": 2,
        "totalElements": 13,
        "totalPages": 7,
        "number": 3
      }
    }

Ví dụ giả định này đang ở trang có `number=3`, tức trang thứ tư theo cách đếm của con người. Mỗi trang có tối đa 2 phần tử, tổng cộng có 13 phần tử và 7 trang.

Các phần quan trọng:

- `_embedded.orders` chứa các bản ghi thuộc trang hiện tại. Tên relation trong `_embedded` thường dựa trên collection relation của repository.
- `_links` chứa các URI điều hướng. Mỗi link có một relation name và một `href`.
- `page.size` là kích thước trang được áp dụng.
- `page.totalElements` là tổng số phần tử phù hợp với truy vấn.
- `page.totalPages` là tổng số trang.
- `page.number` là chỉ số trang hiện tại, bắt đầu từ 0.

Trong response thật, ngoài các link phân trang còn có thể có `self`, `profile`, `search` hoặc các link khác. Không nên giả định response chỉ chứa đúng các trường trong ví dụ.

## 3. Ý nghĩa của từng relation

### first — quay về trang đầu

`first` trỏ tới trang đầu tiên của kết quả. Với quy ước mặc định, trang đầu thường có `page=0`.

Ví dụ:

    "_links": {
      "first": {
        "href": "http://localhost:8080/orders?page=0&size=10"
      }
    }

Client có thể dùng link này khi người dùng chọn nút “Đầu tiên” hoặc muốn quay lại đầu danh sách sau khi xem các trang sau.

### prev — về trang liền trước

`prev` trỏ tới trang ngay trước trang hiện tại.

Nếu client đang ở trang `page=3`, link `prev` thường trỏ tới `page=2`. Đây là một bước lùi, không phải link về trang đầu.

Ở trang đầu tiên không có trang trước, vì vậy server thường bỏ relation `prev`. Client cần hiểu việc thiếu link này là không có bước lùi khả dụng.

### next — sang trang liền sau

`next` trỏ tới trang ngay sau trang hiện tại.

Nếu client đang ở `page=3`, link `next` thường trỏ tới `page=4`. Khi người dùng chọn “Tiếp”, client gọi đúng URI trong `next.href`.

Ở trang cuối cùng không còn trang kế tiếp, vì vậy server thường không trả về relation `next`. Giao diện có thể vô hiệu hóa nút “Tiếp” khi link này không tồn tại.

### last — đi tới trang cuối

`last` trỏ tới trang cuối cùng của kết quả. Ví dụ, khi `totalPages=7`, trang cuối có chỉ số 0-based là 6.

Client không cần tự tính `totalPages - 1` rồi ghép URL. Dùng `last.href` giúp client tuân theo URI thực tế do server tạo ra.

### self — trang hiện tại

Ngoài bốn relation trên, `self` đại diện cho URI của trang hiện tại. Link này hữu ích để lưu hoặc chia sẻ trạng thái danh sách hiện tại, gồm các tham số mà server đã áp dụng.

## 4. Gọi collection resource và lần theo link

Có thể dùng curl để lấy trang đầu:

    curl -i       -H "Accept: application/hal+json"       "http://localhost:8080/orders?page=0&size=10"

Response chứa các link trong `_links`. Để chuyển trang, lấy giá trị `href` của relation cần dùng và gửi request GET tới URI đó:

    curl -i       -H "Accept: application/hal+json"       "http://localhost:8080/orders?page=1&size=10"

Ví dụ thứ hai minh họa URI có thể được gọi; trong ứng dụng thực tế, client nên lấy URI từ `_links.next.href` của response trước thay vì tự tạo `page=1`.

Một client JavaScript đơn giản có thể làm như sau:

    async function loadPage(url) {
      const response = await fetch(url, {
        headers: {
          Accept: "application/hal+json"
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return response.json();
    }

    const current = await loadPage(
      "http://localhost:8080/orders?page=0&size=10"
    );

    const nextHref = current._links?.next?.href;

    if (nextHref) {
      const nextPage = await loadPage(nextHref);
      console.log(nextPage._embedded?.orders ?? []);
    }

Đoạn code kiểm tra sự tồn tại của `next.href` trước khi gọi. Nếu không có link, client không cố điều hướng sang trang tiếp theo.

Trong ứng dụng có base URL, context path hoặc reverse proxy, hãy dùng nguyên URI trong link. Không nên nối hostname hoặc prefix một lần nữa nếu `href` đã là URI đầy đủ.

## 5. Kết hợp phân trang với sorting

Spring Data REST hỗ trợ tham số `sort` cùng với `page` và `size`.

Ví dụ:

    GET /orders?page=0&size=10&sort=createdAt,desc

Request này yêu cầu sắp xếp theo `createdAt` giảm dần. Có thể kết hợp nhiều tiêu chí bằng cách lặp lại tham số `sort`:

    GET /orders?page=0&size=10&sort=status,asc&sort=createdAt,desc

Khi tạo các link phân trang, server có thể giữ lại kích thước trang và tiêu chí sorting đang áp dụng. Do đó, `next.href` và `prev.href` là cách an toàn để đi tiếp trong cùng một tập kết quả.

Để thứ tự giữa các trang ổn định khi nhiều bản ghi có cùng giá trị sort, nên bổ sung một tiêu chí phân biệt duy nhất, chẳng hạn ID:

    GET /orders?page=0&size=10&sort=createdAt,desc&sort=id,desc

Nếu chỉ sắp xếp theo một trường có nhiều giá trị trùng nhau, thứ tự các bản ghi cùng giá trị có thể không ổn định giữa các request. Điều này có thể khiến bản ghi xuất hiện ở trang khác khi dữ liệu thay đổi hoặc khi database trả về thứ tự không xác định cho các giá trị bằng nhau.

Tên thuộc tính dùng trong `sort` là property mà Spring Data nhận diện trong domain model, không mặc định là tên cột database.

## 6. Điều hướng ở trang đầu, trang giữa và trang cuối

Các link có thể xuất hiện khác nhau theo vị trí trang:

| Vị trí | first | prev | next | last |
| --- | --- | --- | --- | --- |
| Trang đầu | Thường có | Không có | Có nếu còn trang sau | Thường có nếu xác định được |
| Trang giữa | Thường có | Có | Có | Thường có nếu xác định được |
| Trang cuối | Thường có | Có nếu có trang trước | Không có | Thường có |
| Chỉ có một trang | Có thể có | Không có | Không có | Có thể cùng trỏ trang duy nhất |

Đây là cách đọc theo ngữ nghĩa. Client phải kiểm tra link thực tế trong từng response; đừng yêu cầu server luôn trả đủ bốn relation. Một số link không áp dụng có thể bị bỏ khỏi `_links`.

Nếu collection rỗng, metadata có thể cho biết `totalElements=0` và `totalPages=0`. Khi đó không có trang dữ liệu tiếp theo để điều hướng. Client nên hiển thị trạng thái rỗng thay vì suy luận rằng một link bị thiếu là lỗi mạng.

## 7. Dùng link để điều khiển giao diện

Một giao diện danh sách có thể hiển thị:

- Nút “Đầu tiên” dựa trên `_links.first`.
- Nút “Trước” dựa trên `_links.prev`.
- Nút “Tiếp” dựa trên `_links.next`.
- Nút “Cuối” dựa trên `_links.last`.
- Thông tin “Trang X / Y” từ `page.number` và `page.totalPages`.

Vì `page.number` bắt đầu từ 0, nếu muốn hiển thị số thứ tự thân thiện với người dùng, có thể hiển thị `page.number + 1`. Đây chỉ là cách trình bày; khi gọi API, client vẫn dùng URI từ HAL.

Ví dụ logic hiển thị:

    const pageNumberForUser = page.page.number + 1;
    const totalPages = page.page.totalPages;

    const canGoFirst = Boolean(page._links?.first?.href);
    const canGoPrevious = Boolean(page._links?.prev?.href);
    const canGoNext = Boolean(page._links?.next?.href);
    const canGoLast = Boolean(page._links?.last?.href);

Giao diện nên dựa trên link có thật để bật/tắt nút. Đừng chỉ dựa vào phép so sánh `number < totalPages - 1` rồi tự tạo URI tiếp theo; cách đó bỏ qua URI và cấu hình mà server đã phát hành.

## 8. Cấu hình kích thước và tên tham số

Spring Data REST có thể cấu hình kích thước trang mặc định và giới hạn kích thước tối đa. Với Spring Boot, các thuộc tính thường dùng trong `application.properties` gồm:

    spring.data.rest.default-page-size=20
    spring.data.rest.max-page-size=100

Kích thước mặc định được áp dụng khi client không gửi `size`. Giới hạn tối đa giúp server kiểm soát request yêu cầu quá nhiều phần tử. Giá trị cụ thể cần được chọn theo dung lượng dữ liệu và chi phí truy vấn của ứng dụng.

Tên các tham số phân trang/sắp xếp mặc định thường là:

- `page`: chỉ số trang.
- `size`: kích thước trang (tham số limit).
- `sort`: tiêu chí sắp xếp.

Spring Data REST cũng cho phép tùy chỉnh tên tham số qua cấu hình repository REST, chẳng hạn `setPageParamName`, `setLimitParamName` và `setSortParamName` trên `RepositoryRestConfiguration`. Khi tên tham số được đổi, URI do server phát ra sẽ phản ánh cấu hình đó. Đây là một lý do khác để client theo link thay vì tự ghép query string.

## 9. Lưu ý khi dữ liệu thay đổi

Các link `first`, `prev`, `next` và `last` mô tả cách điều hướng theo kết quả mà server tạo ra ở thời điểm request. Chúng không bảo đảm snapshot dữ liệu được giữ nguyên giữa nhiều request.

Ví dụ, client đang xem trang thứ hai. Trong lúc đó, một đơn hàng mới được thêm vào đầu danh sách đang sort giảm dần. Khi client gọi link `next`, các bản ghi có thể dịch chuyển giữa các trang. Một số bản ghi có thể lặp lại hoặc bị bỏ qua giữa các lần tải nếu dữ liệu thay đổi đủ nhiều.

Một số cách giảm vấn đề:

1. Dùng sorting ổn định, có thêm trường duy nhất làm tiêu chí cuối.
2. Giữ kích thước trang nhất quán trong suốt một lượt duyệt.
3. Khi nghiệp vụ yêu cầu snapshot nhất quán, thiết kế API và transaction phù hợp thay vì kỳ vọng các link phân trang tự cung cấp snapshot.
4. Với tập dữ liệu rất lớn hoặc cần duyệt liên tục trong môi trường ghi nhiều, cân nhắc cursor/keyset pagination bằng API phù hợp. Các link HAL của Spring Data REST mặc định thường mô hình hóa phân trang theo page/size.

## 10. Các lỗi thường gặp

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Không có `next` | Đang ở trang cuối, chỉ có một trang hoặc không có dữ liệu; kiểm tra `page.totalPages` và các link còn lại |
| Không có `prev` | Đang ở trang đầu; đây thường là trạng thái hợp lệ |
| Không có `first` hoặc `last` | Kiểm tra response thực tế, loại resource, cấu hình và khả năng xác định trang; client phải chấp nhận link không có |
| 400 Bad Request | Giá trị `page`, `size`, `sort` không hợp lệ hoặc tên thuộc tính sort không được hỗ trợ |
| Số phần tử ít hơn `size` | Có thể đang ở trang cuối; `size` là số lượng tối đa, không phải cam kết trang nào cũng đủ phần tử |
| Link không truy cập được | Kiểm tra base path, proxy, hostname, authentication và quyền truy cập |
| Bản ghi lặp hoặc thiếu giữa các trang | Kiểm tra sorting có ổn định không và dữ liệu có thay đổi giữa các request không |

Khi debug, làm theo thứ tự:

1. Gửi GET collection resource với `Accept: application/hal+json`.
2. Đọc `page.number`, `page.totalPages` và `page.totalElements`.
3. Kiểm tra relation cần dùng có trong `_links` hay không.
4. Gọi đúng `href` và giữ nguyên các header xác thực/representation cần thiết.
5. Nếu link trả lỗi, kiểm tra URL bên ngoài, base path, reverse proxy và Spring Security.

## 11. Bài thực hành

Giả sử repository `OrderRepository` được xuất bản ở `/orders`. Có 23 đơn hàng và client yêu cầu mỗi trang 5 đơn hàng, sắp xếp theo thời gian tạo mới nhất trước:

    GET /orders?page=0&size=5&sort=createdAt,desc
    Accept: application/hal+json

Thực hiện:

1. Gọi request trên và đọc `page.totalElements`, `page.totalPages`, `page.number`.
2. Lấy `_links.next.href` và gọi link đó để tải trang tiếp theo.
3. Từ trang giữa, dùng `_links.prev.href` để quay lại.
4. Dùng `_links.first.href` để quay về đầu danh sách.
5. Dùng `_links.last.href` để đi tới trang cuối.
6. Ở trang cuối, xác nhận relation `next` không còn nếu không có trang sau.
7. Thử thêm tiêu chí `sort=id,desc` để tạo thứ tự ổn định khi `createdAt` trùng nhau.
8. Thử gọi API với kích thước trang vượt giới hạn cấu hình và quan sát cách server xử lý.

Câu hỏi tự kiểm tra:

- Vì sao `page=0` là trang đầu tiên?
- Relation `prev` khác `first` như thế nào?
- Vì sao client nên gọi `next.href` thay vì tự tăng `page`?
- Khi nào `next` không xuất hiện trong response?
- Sorting ổn định giúp hạn chế vấn đề gì khi điều hướng nhiều trang?

## Tài liệu tham khảo

- [Spring Data REST Reference — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data Commons Reference — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
