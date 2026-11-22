# Kết hợp tham số nghiệp vụ với Pageable và Sort

Một search endpoint trong Spring Data REST thường cần nhận cả điều kiện nghiệp vụ và yêu cầu phân trang, sắp xếp. Ví dụ, client muốn tìm các đơn hàng đã thanh toán của một khách hàng, chỉ lấy 20 kết quả mỗi trang và sắp xếp theo ngày tạo mới nhất. Các tham số nghiệp vụ xác định **bản ghi nào phù hợp**; `Pageable` và `Sort` xác định **kết quả được chia trang và sắp thứ tự ra sao**.

## 1. Tách tham số lọc khỏi tham số phân trang

Giả sử domain có entity `Order` với các thuộc tính `status`, `customer` và `createdAt`. Một truy vấn có thể cần:

- Tham số nghiệp vụ: `status` để lọc trạng thái đơn hàng.
- Tham số nghiệp vụ: `customerId` để lọc theo khách hàng.
- Tham số phân trang: `page` để chọn trang.
- Tham số phân trang: `size` để giới hạn số phần tử trên trang.
- Tham số sắp xếp: `sort` để chọn thuộc tính và chiều sắp xếp.

Ví dụ request:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc
Accept: application/hal+json
```

Trong request này, `status` và `customerId` là tiêu chí tìm kiếm của ứng dụng. `page`, `size` và `sort` là tham số hạ tầng của Spring Data để điều khiển cách lấy kết quả.

Tách hai nhóm này giúp API rõ ràng: thêm một bộ lọc nghiệp vụ không làm thay đổi cách phân trang, còn thay đổi page size hoặc sort không làm thay đổi điều kiện lọc.

## 2. Khai báo query method nhận Pageable

Spring Data repository hỗ trợ truyền `Pageable` vào query method. Ví dụ:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Page<Order> findByStatusAndCustomer_Id(
        @Param("status") OrderStatus status,
        @Param("customerId") Long customerId,
        Pageable pageable
    );
}
```

Trong đó:

- `findByStatusAndCustomer_Id` là derived query method: Spring Data phân tích tên method để tạo điều kiện lọc theo status và id của customer.
- `@Param("status")` công bố tên query parameter `status`.
- `@Param("customerId")` công bố tên query parameter `customerId`.
- `Pageable pageable` yêu cầu Spring Data áp dụng page, size và sort cho truy vấn.
- `Page<Order>` cho biết kết quả có thông tin trang, bao gồm số phần tử và tổng số kết quả theo truy vấn.

Tham số `Pageable` là tham số đặc biệt của Spring Data. Không cần khai báo nó như một tham số nghiệp vụ bằng `@Param`. Spring Data REST nhận biết các tham số phân trang và sắp xếp, sau đó chuyển chúng thành đối tượng `Pageable` khi gọi repository method.

Nếu muốn URL của search method dễ đọc hơn, có thể tùy chỉnh path và relation:

```java
@RestResource(
    path = "by-status-and-customer",
    rel = "byStatusAndCustomer"
)
Page<Order> findByStatusAndCustomer_Id(
    @Param("status") OrderStatus status,
    @Param("customerId") Long customerId,
    Pageable pageable
);
```

Search link được công bố trong HAL là điểm khám phá endpoint. Path và relation thực tế phụ thuộc cấu hình export; ví dụ trên minh họa một cách đặt tên.

## 3. Pageable điều khiển page và size

`Pageable` gom các thông tin cần thiết để lấy một phần kết quả:

- `page`: chỉ số trang, bắt đầu từ 0.
- `size`: số phần tử tối đa muốn lấy trong một trang.
- `sort`: thứ tự sắp xếp trước khi chia trang.

Ví dụ:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=1&size=20
Accept: application/hal+json
```

`page=1` nghĩa là trang thứ hai theo cách đánh số từ 0. Với `size=20`, client yêu cầu tối đa 20 đơn hàng trên trang đó.

Spring Data REST có cấu hình page size mặc định và giới hạn tối đa. Có thể điều chỉnh thông qua `RepositoryRestConfiguration`, chẳng hạn:

```java
@Configuration
public class RestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
```

Các giá trị 20 và 100 trong ví dụ là lựa chọn cấu hình minh họa, không phải giới hạn cố định của Spring Data REST. Nên đặt max page size phù hợp với dung lượng response, hiệu năng truy vấn và khả năng của client. Giới hạn này giúp tránh request yêu cầu một trang quá lớn gây tải không cần thiết.

Nếu bỏ `page` hoặc `size`, Spring Data REST dùng giá trị mặc định theo cấu hình. Client không nên giả định default page size giống nhau ở mọi môi trường.

## 4. Sort sắp xếp kết quả trước khi phân trang

`Sort` mô tả thuộc tính dùng để sắp xếp và chiều sắp xếp. Với tham số URL của Spring Data REST, dạng thông dụng là:

`sort=property,direction`

Trong đó:

- `property` là tên thuộc tính domain cần sắp xếp.
- `direction` là `asc` (tăng dần) hoặc `desc` (giảm dần).

Ví dụ sắp xếp theo ngày tạo mới nhất:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc
```

Có thể truyền nhiều tiêu chí sort bằng cách lặp lại tham số `sort`:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc&sort=id,asc
```

Ví dụ này ưu tiên `createdAt` giảm dần; nếu nhiều đơn hàng có cùng thời điểm tạo, `id` tăng dần được dùng làm tiêu chí tiếp theo. Thêm một tiêu chí phụ ổn định giúp phân trang ít bị xáo trộn khi nhiều bản ghi có cùng giá trị sort chính.

Tên sort thường là property path trong domain model, không phải tên cột SQL hay tên field đã đổi trong JSON representation. Ví dụ `customer.name` có thể là một property path nếu query và mapping hỗ trợ. Cần dùng thuộc tính mà repository có thể sắp xếp; field không tồn tại hoặc không hỗ trợ sort có thể khiến request thất bại.

Sort cũng cần được kiểm soát theo nhu cầu API. Không nên để client yêu cầu tùy ý những thuộc tính đắt đỏ hoặc nhạy cảm; có thể giới hạn sort keys được hỗ trợ ở tầng API/service và tối ưu index database cho các cách sắp xếp thường dùng.

## 5. Kết hợp bộ lọc, Pageable và Sort trong một request

Một request đầy đủ có thể chứa nhiều tham số nghiệp vụ cùng tham số phân trang:

```http
GET /orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20&sort=createdAt,desc&sort=id,asc
Accept: application/hal+json
```

Server xử lý theo ý nghĩa khái quát:

1. Bind `status` và `customerId` vào tham số của query method.
2. Chuyển `page`, `size` và `sort` thành `Pageable`.
3. Repository thực hiện query với điều kiện nghiệp vụ và thông tin phân trang/sắp xếp.
4. Spring Data REST biểu diễn kết quả và metadata trang theo representation được cấu hình.

Điều kiện lọc quyết định tập kết quả. Sắp xếp được áp dụng lên tập kết quả phù hợp trước khi lấy phần tử của trang. Do đó, page 0 và page 1 phải dùng cùng điều kiện lọc và thứ tự sắp xếp nếu client muốn duyệt một kết quả nhất quán.

Nếu client thay đổi `status` hoặc `customerId` trong khi đang ở page 4, nên quay lại page 0 vì tập kết quả đã thay đổi. Tương tự, khi thay đổi sort, các ranh giới trang có thể thay đổi.

## 6. Phân biệt Page, Slice, List và Sort

Kiểu trả về của query method quyết định metadata mà client nhận được:

| Kiểu trả về | Ý nghĩa |
|---|---|
| `Page<T>` | Có nội dung trang và metadata như total elements, total pages |
| `Slice<T>` | Có nội dung và thông tin còn trang tiếp theo hay không; không yêu cầu tổng số phần tử toàn bộ |
| `List<T>` | Danh sách kết quả; không có page metadata như `Page` |
| `T` hoặc `Optional<T>` | Một kết quả đơn hoặc có thể không có kết quả; không phải collection phân trang |

Khi giao diện cần hiển thị tổng số kết quả, số trang và điều khiển chuyển trang, `Page<T>` thường phù hợp. Nếu chỉ cần biết có thể tải tiếp hay không và muốn tránh truy vấn đếm tổng, `Slice<T>` có thể phù hợp hơn khi repository và endpoint hỗ trợ kiểu trả về đó.

Một query method nhận `Sort` có thể dùng khi chỉ cần sắp xếp mà không cần page/size. Nếu dùng `Pageable`, thông tin sort đã nằm trong pageable; không cần khai báo thêm một tham số `Sort` riêng cho cùng method. Chọn một cơ chế theo nhu cầu của method và hỗ trợ của Spring Data.

## 7. Response phân trang trong HAL

Với query method trả về `Page<Order>`, Spring Data REST có thể trả representation collection theo HAL, bao gồm các liên kết điều hướng và metadata trang. Ví dụ rút gọn:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=0&size=20"
    },
    "next": {
      "href": "https://api.example.test/orders/search/byStatusAndCustomer?status=PAID&customerId=42&page=1&size=20"
    },
    "profile": {
      "href": "https://api.example.test/profile/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": 501,
        "status": "PAID"
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 47,
    "totalPages": 3,
    "number": 0
  }
}
```

Đây là response minh họa. Tên collection relation, các link, field và metadata thực tế phụ thuộc repository resource rel, cấu hình projection và phiên bản Spring Data REST.

Client nên theo link `next` hoặc `prev` do server cung cấp khi có, giữ nguyên tham số nghiệp vụ và sort. Không nên tự ghép URL trang tiếp theo bằng cách bỏ mất filter hoặc sort hiện tại.

## 8. Lỗi thường gặp và cách xử lý

| Vấn đề | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Search method không xuất hiện | Method không được export hoặc repository không công bố query method | Kiểm tra `@RestResource`, repository export và search link |
| Tham số nghiệp vụ không bind | Tên query parameter không khớp tên `@Param` hoặc kiểu dữ liệu không chuyển đổi được | Kiểm tra tên tham số và converter |
| Page luôn trở về trang đầu | Thiếu `page` hoặc client gửi sai chỉ số trang | Gửi page dạng zero-based |
| Kết quả có ít phần tử hơn size | Trang cuối, filter không có đủ kết quả hoặc server áp dụng max page size | Đọc metadata trang và cấu hình giới hạn |
| Sort không hoạt động hoặc báo lỗi | Property path sai hoặc method không hỗ trợ thuộc tính đó | Dùng tên property domain hợp lệ |
| Trang bị trùng hoặc thiếu item khi dữ liệu thay đổi | Sort không ổn định hoặc bản ghi được thêm/xóa giữa các request | Thêm tiêu chí sort duy nhất và xem xét cơ chế snapshot/scroll phù hợp |
| Query chậm | Filter, sort hoặc count query không có index phù hợp | Kiểm tra execution plan và tối ưu index |

Đặc biệt, phân trang theo offset không tự bảo đảm snapshot nhất quán khi dữ liệu thay đổi liên tục. Nếu có bản ghi mới được thêm trước vị trí hiện tại giữa hai lần tải trang, client có thể thấy phần tử lặp hoặc bị bỏ qua. Một sort ổn định với khóa phụ duy nhất giảm sự xáo trộn do giá trị trùng, nhưng không thay thế snapshot hoặc cursor-based pagination nếu nghiệp vụ cần duyệt một tập dữ liệu thay đổi liên tục.

## 9. Ví dụ hoàn chỉnh từ repository đến client

Repository:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(
        path = "by-status-and-customer",
        rel = "byStatusAndCustomer"
    )
    Page<Order> findByStatusAndCustomer_Id(
        @Param("status") OrderStatus status,
        @Param("customerId") Long customerId,
        Pageable pageable
    );
}
```

Client:

```bash
curl -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "status=PAID" \
  --data-urlencode "customerId=42" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=createdAt,desc" \
  --data-urlencode "sort=id,asc" \
  https://api.example.test/orders/search/by-status-and-customer
```

Request này lọc đơn hàng theo trạng thái và khách hàng, lấy trang đầu với tối đa 20 phần tử, sắp xếp theo ngày tạo giảm dần rồi id tăng dần. Server có thể trả HAL collection cùng metadata phân trang để client tiếp tục theo các link điều hướng.

## 10. Checklist thiết kế search endpoint

1. Đưa điều kiện nghiệp vụ vào các tham số query method có tên rõ ràng.
2. Dùng `@Param` để công bố tên query parameter ổn định cho client.
3. Dùng `Pageable` khi cần page, size và sort cùng lúc; dùng `Sort` khi chỉ cần sắp xếp.
4. Trả `Page<T>` khi client cần tổng số phần tử và tổng số trang.
5. Đặt default page size và max page size phù hợp với tải hệ thống.
6. Công bố search method bằng repository export và tùy chỉnh path/relation khi cần.
7. Chỉ hỗ trợ các sort property phù hợp, thêm tiêu chí phụ duy nhất khi cần thứ tự ổn định.
8. Khi duyệt các trang tiếp theo, giữ nguyên filter và sort hoặc theo trực tiếp HAL navigation links.
9. Kiểm tra index và count query cho các tổ hợp filter/sort thường dùng.

Khi kết hợp đúng tham số nghiệp vụ với `Pageable` và `Sort`, một search method có thể phục vụ truy vấn cụ thể mà vẫn hỗ trợ phân trang và sắp xếp nhất quán. Client kiểm soát điều kiện tìm kiếm qua query parameters, còn Spring Data REST và Spring Data xử lý phần phân trang, thứ tự và hypermedia navigation theo hợp đồng đã công bố.
