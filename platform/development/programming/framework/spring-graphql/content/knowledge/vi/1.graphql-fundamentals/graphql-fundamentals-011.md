# Giới hạn của GraphQL

## Nền tảng GraphQL

GraphQL cho phép client mô tả chính xác dữ liệu cần nhận trong một operation. Cách tiếp cận này giúp giảm tình trạng lấy thừa hoặc thiếu dữ liệu thường gặp khi một API REST phải phục vụ nhiều màn hình và nhiều loại client. Schema có kiểu dữ liệu rõ ràng cũng giúp client khám phá API và phát hiện một số lỗi ngay trong quá trình phát triển.

Tuy nhiên, GraphQL không tự động làm cho hệ thống nhanh hơn, an toàn hơn hay dễ vận hành hơn. Nó chuyển một phần quyền quyết định cấu trúc truy vấn sang client, đồng thời đặt thêm trách nhiệm lên server: kiểm soát chi phí truy vấn, phối hợp việc tải dữ liệu, bảo vệ từng trường và quan sát hoạt động của API. Hiểu những giới hạn này giúp chọn GraphQL đúng chỗ và thiết kế Spring for GraphQL có kiểm soát.

## 1. GraphQL không bảo đảm hiệu năng tốt hơn

GraphQL là ngôn ngữ truy vấn và cơ chế thực thi API. Nó không quyết định database được truy vấn thế nào, không tự tạo index và cũng không bảo đảm một operation chỉ tạo ra một câu SQL.

Ví dụ, client gửi một request để lấy danh sách sách cùng tác giả:

```graphql
query BookList {
  books(first: 20) {
    title
    author {
      name
    }
  }
}
```

Server có thể xử lý `books` bằng một truy vấn, sau đó gọi resolver `author` riêng cho từng quyển sách. Khi đó một request GraphQL có thể tạo ra nhiều lần truy cập database hoặc nhiều lời gọi đến service khác. Số lượng request HTTP ít không đồng nghĩa với số lượng thao tác backend ít.

Hiệu năng phụ thuộc vào cách triển khai resolver, mô hình dữ liệu, chiến lược truy vấn, cache và giới hạn tài nguyên. Cần đo thời gian thực thi và số lần truy cập backend thay vì đánh giá hiệu năng chỉ bằng số request từ client.

## 2. Query linh hoạt có thể tạo ra chi phí lớn

Client có thể chọn nhiều trường, lồng nhiều quan hệ hoặc yêu cầu nhiều bản ghi trong cùng một operation. Sự linh hoạt này cũng tạo cơ hội cho truy vấn tốn tài nguyên ngoài dự kiến.

Ví dụ minh họa một truy vấn có phạm vi lớn:

```graphql
query LargeReport {
  customers(first: 100) {
    orders(first: 100) {
      items(first: 100) {
        product {
          reviews(first: 100) {
            rating
          }
        }
      }
    }
  }
}
```

Nếu mỗi cấp trả về nhiều phần tử, số lượng đối tượng cần tải và xử lý có thể tăng rất nhanh. Một truy vấn không sâu vẫn có thể rất rộng; ngược lại, một truy vấn sâu chưa chắc tốn kém nếu mỗi nhánh chỉ trả về ít dữ liệu. Vì vậy, chỉ giới hạn độ sâu là chưa đủ để kiểm soát mọi loại truy vấn.

Server nên kết hợp nhiều biện pháp:

- Phân trang cho danh sách và đặt giới hạn tối đa cho kích thước mỗi trang.
- Giới hạn độ sâu, số lượng alias hoặc độ phức tạp ước tính của operation khi phù hợp.
- Đặt timeout và giới hạn tài nguyên cho các thao tác tốn kém.
- Áp dụng rate limit theo người dùng, ứng dụng hoặc API key.
- Theo dõi những operation có thời gian thực thi, số bản ghi hoặc chi phí backend bất thường.
- Cân nhắc persisted query hoặc allowlist operation cho các client được kiểm soát.

Độ phức tạp truy vấn là một ước lượng dựa trên schema và chính sách của hệ thống, không phải con số chính xác tuyệt đối về thời gian chạy. Các trường gọi dịch vụ bên ngoài, tìm kiếm toàn văn hoặc tính toán nghiệp vụ có thể có chi phí khác nhau dù số trường trong query giống nhau.

Trong Spring for GraphQL, có thể đặt kiểm soát ở lớp tiếp nhận request và lớp thực thi GraphQL, đồng thời dùng các cơ chế giới hạn ở service hoặc database. Không nên chỉ dựa vào giao diện client để ngăn truy vấn lớn, vì client có thể bị sửa đổi hoặc request có thể được gửi trực tiếp.

## 3. Vấn đề N+1 khi phân giải field

Một hạn chế thường gặp khi triển khai GraphQL là vấn đề N+1. Server tải một danh sách gồm N phần tử, sau đó mỗi phần tử lại kích hoạt một truy vấn riêng để lấy dữ liệu của field liên quan.

Ví dụ resolver Spring for GraphQL sau có thể tạo ra một lần truy vấn tác giả cho mỗi quyển sách:

```java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book book) {
    return authorRepository.findById(book.authorId()).orElse(null);
}
```

Nếu query lấy 20 quyển sách, server có thể thực hiện một truy vấn lấy sách và thêm 20 truy vấn lấy tác giả. Với một danh sách lớn hoặc nhiều cấp quan hệ, số lần truy cập dữ liệu tăng nhanh và làm giảm hiệu năng.

Các hướng xử lý phổ biến gồm:

1. Tải dữ liệu liên quan theo lô thay vì tải từng phần tử.
2. Dùng DataLoader để gom các yêu cầu trong cùng một lần thực thi thành một lần tải theo batch và chia kết quả lại cho từng field.
3. Dùng `@BatchMapping` của Spring for GraphQL khi quan hệ field phù hợp với cơ chế batch mapping.
4. Tối ưu truy vấn repository và database; chỉ lấy những cột cần thiết khi điều đó có ích.

DataLoader giúp giảm số lần gọi backend nhưng không thay thế phân trang hoặc giới hạn chi phí truy vấn. Một batch chứa hàng chục nghìn khóa vẫn có thể gây áp lực lên database. Cache của DataLoader thường được tổ chức theo lần thực thi request; không nên mặc định dùng nó như cache dùng chung giữa nhiều người dùng.

## 4. Cache HTTP và CDN phức tạp hơn

Với REST, mỗi tài nguyên thường có URL riêng, chẳng hạn `/books/42`. Điều này giúp cache HTTP và CDN nhận diện tài nguyên theo URL, kết hợp với các header như `Cache-Control`, `ETag` và `Vary`.

Với GraphQL, nhiều loại dữ liệu và nhiều operation có thể đi qua cùng một endpoint, ví dụ `/graphql`. Hai request đến cùng endpoint có thể yêu cầu dữ liệu hoàn toàn khác nhau. Nếu chỉ dùng URL làm cache key, cache có thể trả nhầm kết quả.

Cache GraphQL cần tính đến nội dung operation, biến truyền vào, danh tính hoặc quyền truy cập của người dùng và chính sách hết hạn. Query thường có thể được gửi bằng POST; một số triển khai hỗ trợ GET cho query để tận dụng cache HTTP, nhưng mutation không nên được gửi bằng GET. Persisted query giúp nhận diện operation ổn định hơn, song vẫn cần xử lý biến và ngữ cảnh phân quyền trong cache key.

GraphQL vẫn có thể dùng cache ở nhiều tầng:

- Cache dữ liệu tại service hoặc repository.
- Cache theo operation và biến đầu vào khi dữ liệu cho phép chia sẻ an toàn.
- Cache phía client theo từng field hoặc normalized entity.
- Cache HTTP/CDN khi transport, cache key và chính sách bảo mật được thiết kế phù hợp.

Điểm cần nhớ là cache phải gắn với ngữ cảnh quyền truy cập. Không được dùng chung kết quả có chứa dữ liệu riêng tư giữa hai người dùng chỉ vì họ gửi cùng một query.

## 5. Bảo mật phải áp dụng đến từng field

Một schema GraphQL có thể tạo ra nhiều đường đi đến cùng một dữ liệu. Người dùng có thể truy vấn một field thông qua nhiều quan hệ khác nhau, vì vậy chỉ kiểm tra quyền ở resolver gốc là chưa đủ trong mọi thiết kế.

Giả sử API có `me`, `user(id)`, `orders` và `customer`. Nếu chỉ kiểm tra quyền tại query `user`, một field khác có thể vô tình làm lộ thông tin người dùng hoặc đơn hàng mà caller không được phép xem.

Thiết kế bảo mật cần xác định rõ:

- Ai được gọi operation và ai được truy cập từng đối tượng?
- Người dùng có được xem hoặc thay đổi field cụ thể hay không?
- Quyền có phụ thuộc vào trạng thái nghiệp vụ, chủ sở hữu bản ghi hoặc tenant không?
- Resolver có thể gọi service nội bộ nào, và service đó có kiểm tra quyền cần thiết không?

Trong Spring for GraphQL, có thể kết hợp xác thực ở tầng HTTP, kiểm tra quyền ở resolver bằng Spring Security và kiểm tra quy tắc nghiệp vụ trong service. Cần áp dụng kiểm tra ở nơi có đủ ngữ cảnh để xác minh quyền đối với đối tượng và thao tác. Không nên xem việc ẩn field khỏi schema hoặc tắt introspection là biện pháp phân quyền.

Thông báo lỗi cũng cần được kiểm soát. Exception nội bộ, câu SQL, token, thông tin cấu hình hoặc dữ liệu nhạy cảm không nên xuất hiện trong response gửi client. Quyền truy cập phải được kiểm tra ở server cho mọi request, kể cả operation được lưu sẵn.

## 6. Xử lý lỗi và kết quả một phần cần được hiểu đúng

Một response GraphQL có thể chứa cả `data` và `errors`. Điều này xảy ra khi một số field được phân giải thành công nhưng một field khác gặp lỗi. Vì vậy, client không thể chỉ dựa vào HTTP status code hoặc giả định rằng một request chỉ có hai trạng thái thành công và thất bại.

Ví dụ response minh họa:

```json
{
  "data": {
    "book": {
      "title": "GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải thông tin tác giả",
      "path": ["book", "author"]
    }
  ]
}
```

Client cần đọc cả `data` lẫn `errors`, sau đó quyết định có thể hiển thị phần dữ liệu đã tải được hay phải báo lỗi toàn màn hình. Nếu field được khai báo non-null trong schema, lỗi ở field đó có thể lan lên field cha gần nhất cho phép nhận `null`; vì vậy lựa chọn nullable hay non-null ảnh hưởng trực tiếp đến phạm vi dữ liệu còn lại trong response.

Ở server, nên chuẩn hóa mã lỗi và phần `extensions` khi cần cung cấp thông tin máy đọc được. Log nội bộ có thể chứa chi tiết phục vụ điều tra, còn response gửi client chỉ nên chứa thông tin an toàn và hữu ích. Với Spring for GraphQL, `DataFetcherExceptionResolver` là một trong những điểm mở rộng để ánh xạ exception từ resolver thành lỗi GraphQL có cấu trúc.

## 7. Schema cần được quản lý khi có nhiều client

Schema GraphQL là hợp đồng dùng chung giữa server và nhiều client. Khi số lượng ứng dụng tăng, một thay đổi tưởng như nhỏ có thể ảnh hưởng đến nhiều nhóm phát triển.

Ví dụ, đổi tên field hoặc thay đổi kiểu dữ liệu có thể làm query đang chạy của client cũ thất bại. Xóa một field ngay khi server không còn dùng đến cũng có thể phá vỡ ứng dụng chưa kịp cập nhật.

Để giảm rủi ro:

- Ưu tiên bổ sung field mới theo cách tương thích ngược.
- Đánh dấu field cũ bằng directive `@deprecated` và cung cấp lý do hoặc field thay thế.
- Theo dõi mức sử dụng field và operation trước khi loại bỏ API cũ.
- Thống nhất quy tắc đặt tên, nullable, pagination và cấu trúc lỗi.
- Kiểm thử schema và operation đại diện của các client trước khi phát hành.

GraphQL có introspection và hệ sinh thái công cụ hỗ trợ khám phá schema, nhưng các công cụ này không tự giải quyết quy trình quản lý phiên bản, thông báo thay đổi hay phối hợp phát hành giữa các nhóm.

## 8. Subscription và dữ liệu nhị phân có yêu cầu riêng

Query và mutation thường phù hợp với request-response. Subscription lại cần một kết nối hoặc kênh truyền có thể duy trì để server gửi sự kiện đến client. Điều này làm phát sinh thêm vấn đề về số kết nối đồng thời, xác thực trong suốt vòng đời kết nối, reconnect, xử lý client chậm, phân phối sự kiện giữa nhiều instance và khả năng mở rộng hạ tầng.

Subscription phù hợp khi client thực sự cần nhận cập nhật liên tục. Với dữ liệu không cần thời gian thực, polling có chu kỳ hợp lý hoặc cơ chế thông báo khác có thể đơn giản hơn. Cũng cần xác định rõ subscription phát sự kiện theo quyền của người dùng nào và xử lý việc quyền thay đổi sau khi kết nối đã được thiết lập.

GraphQL core không định nghĩa một scalar upload file chuẩn dùng chung cho mọi triển khai. Một số hệ thống hỗ trợ upload qua phần mở rộng multipart, nhưng client và server phải thống nhất giao thức. Với file lớn, cách phổ biến là dùng GraphQL để tạo yêu cầu upload hoặc cấp URL đã ký, sau đó truyền file trực tiếp đến object storage. Cách này tránh đưa luồng byte lớn qua resolver GraphQL và giúp tận dụng cơ chế upload chuyên dụng.

## 9. Vận hành và quan sát API cần nhiều ngữ cảnh hơn

Trong REST, đường dẫn và HTTP method thường giúp nhóm vận hành nhận diện loại thao tác. Trong GraphQL, rất nhiều operation có thể dùng chung một endpoint, còn tên field không nhất thiết thể hiện đầy đủ chi phí backend.

Nếu chỉ thống kê số request đến `/graphql`, nhóm vận hành khó biết query nào chậm, field nào thường lỗi hoặc resolver nào tạo nhiều truy vấn database. Log toàn bộ query và biến cũng có thể làm lộ dữ liệu nhạy cảm hoặc tạo lượng log quá lớn.

Một hệ thống GraphQL nên quan sát operation name, thời gian thực thi, lỗi, mức sử dụng field và thời gian của các resolver quan trọng. Cần che hoặc loại bỏ dữ liệu nhạy cảm khỏi log, đặt giới hạn kích thước request và giữ khả năng truy vết từ operation xuống các lời gọi service hoặc database. Persisted operation cũng giúp nhận diện nhóm query phổ biến và kiểm soát tốt hơn các client đã biết.

## 10. Khi nào nên chọn GraphQL?

GraphQL thường phù hợp khi nhiều client cần các tổ hợp dữ liệu khác nhau, dữ liệu có quan hệ dạng graph và việc để client chọn field giúp giảm số vòng gọi API. Nó cũng hữu ích khi một nhóm server muốn công bố schema có kiểu rõ ràng cho nhiều ứng dụng cùng sử dụng.

REST có thể phù hợp hơn khi API chủ yếu cung cấp các tài nguyên đơn giản, cần tận dụng cache HTTP/CDN trực tiếp, có luồng tải file lớn hoặc có hợp đồng endpoint ổn định và dễ vận hành. Một hệ thống cũng có thể dùng REST cho một số luồng và GraphQL cho những màn hình cần truy vấn kết hợp; không bắt buộc mọi chức năng phải dùng cùng một kiểu API.

| Nhu cầu | Điều cần cân nhắc |
| --- | --- |
| Nhiều client cần các tập field khác nhau | GraphQL có thể giảm việc tạo nhiều endpoint theo từng màn hình |
| Query có nhiều quan hệ lồng nhau | Cần DataLoader, batch mapping, phân trang và giới hạn chi phí |
| Dữ liệu công khai cần CDN cache đơn giản | REST thường dễ cấu hình cache theo URL hơn |
| Quyền truy cập khác nhau theo field hoặc đối tượng | Cần thiết kế authorization ở resolver và service |
| Cập nhật thời gian thực | Subscription có thể phù hợp nếu hệ thống đáp ứng được yêu cầu kết nối lâu dài |
| Upload hoặc download file lớn | Nên cân nhắc luồng truyền file chuyên dụng và dùng API để điều phối |

## 11. Checklist trước khi đưa GraphQL vào production

- [ ] Các field danh sách đều có pagination và giới hạn kích thước hợp lý.
- [ ] Đã kiểm tra query depth, query complexity hoặc chính sách giới hạn tương đương.
- [ ] Các quan hệ có nguy cơ N+1 đã được đo và xử lý bằng batch loading khi phù hợp.
- [ ] Resolver và service kiểm tra quyền truy cập theo người dùng, đối tượng và thao tác.
- [ ] Cache key có xét đến operation, biến và ngữ cảnh phân quyền.
- [ ] Client xử lý được response có cả `data` và `errors`.
- [ ] Schema có quy trình deprecate và kiểm tra tương thích trước khi xóa field.
- [ ] Subscription, nếu có, đã có chính sách xác thực, reconnect và giới hạn kết nối.
- [ ] Log và tracing giúp xác định operation hoặc resolver chậm mà không làm lộ dữ liệu nhạy cảm.

## Kết luận

GraphQL giải quyết tốt bài toán để client chọn cấu trúc dữ liệu cần nhận, nhưng sự linh hoạt đó đòi hỏi server kiểm soát chặt chi phí thực thi và quyền truy cập. Những vấn đề cần chú ý nhất khi xây dựng API là query quá lớn, N+1, cache, bảo mật theo field, xử lý lỗi một phần, tiến hóa schema và vận hành subscription.

Với Spring for GraphQL, các resolver được tổ chức qua `@SchemaMapping`, còn `@BatchMapping` và DataLoader hỗ trợ gom việc tải dữ liệu liên quan. Những công cụ này phát huy hiệu quả khi đi cùng phân trang, giới hạn truy vấn, kiểm tra quyền, xử lý lỗi và quan sát hệ thống. Chọn GraphQL khi lợi ích từ schema và khả năng truy vấn linh hoạt lớn hơn chi phí vận hành mà nó mang lại.
