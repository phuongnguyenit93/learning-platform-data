# Tên method và khả năng đọc contract

Trong gRPC, tên method là một phần của **contract công khai** giữa client và server. Một tên rõ ràng giúp người đọc đoán đúng nghiệp vụ, nhận ra chiều dữ liệu và hiểu loại kết quả mà lời gọi cung cấp trước khi mở phần triển khai Java. Ngược lại, các tên chung chung như **Process**, **Handle** hay **DoRequest** khiến người dùng phải đọc code server mới biết lời gọi thực sự làm gì.

Với **Spring gRPC**, contract được khai báo trong file **.proto**; tên service và method còn tham gia tạo đường dẫn RPC, descriptor và API stub Java. Vì vậy, đặt tên cần nhất quán ngay từ đầu và phải được xem như một quyết định thiết kế API.

## 1. Đọc một method từ tên đến contract

Một khai báo gRPC thường có dạng:

~~~proto
rpc GetProduct(GetProductRequest) returns (GetProductResponse);
~~~

Người đọc có thể hiểu ba phần:

- **GetProduct**: hành động nghiệp vụ mà client yêu cầu.
- **GetProductRequest**: dữ liệu client phải cung cấp.
- **GetProductResponse**: dữ liệu server trả về khi thành công.

Tên method cho biết *làm việc gì*; kiểu request và response cho biết *cần dữ liệu nào và nhận kết quả gì*. Từ khóa **stream** cho biết một phía có thể gửi nhiều message trong cùng RPC. Cả ba yếu tố phải nhất quán để contract tự giải thích được.

Ví dụ, hai khai báo sau có cardinality khác nhau dù tên method gần giống:

~~~proto
rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
rpc WatchOrderUpdates(WatchOrderUpdatesRequest)
    returns (stream OrderUpdate);
~~~

**ListOrders** trả một response, thường chứa một trang danh sách. **WatchOrderUpdates** trả một luồng event theo thời gian. Người đọc không cần suy luận cardinality từ tên; kiểu trả về trong .proto xác định chính xác điều đó.

## 2. Quy ước đặt tên service, method và message

Nên dùng quy ước nhất quán theo Protobuf:

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Package | chữ thường, phân cấp theo domain và phiên bản | **acme.inventory.v1** |
| Service | PascalCase, tên miền/chức năng | **InventoryService** |
| RPC method | PascalCase, động từ + đối tượng hoặc hành động rõ nghĩa | **GetProduct**, **ReserveStock** |
| Request/response message | PascalCase, gắn với method hoặc khái niệm nghiệp vụ | **ReserveStockRequest**, **Reservation** |
| Field | lower_snake_case | **product_id**, **requested_quantity** |
| Enum type | PascalCase | **ReservationStatus** |
| Enum value | UPPER_SNAKE_CASE, có prefix theo enum khi phù hợp | **RESERVATION_STATUS_CONFIRMED** |

Tên service nên thể hiện **ranh giới năng lực**. **InventoryService** dễ hiểu hơn **CommonService** hoặc **GrpcService**, vì người dùng biết service chịu trách nhiệm về tồn kho. Một service có thể có nhiều RPC liên quan cùng domain; không nên gom các thao tác không liên quan vào một service chỉ vì chúng dùng chung hạ tầng.

Tên method nên bắt đầu bằng động từ diễn tả hành động:

- **GetProduct**: đọc một sản phẩm theo định danh.
- **CreateOrder**: tạo đơn hàng.
- **CancelOrder**: hủy đơn hàng.
- **ListOrders**: liệt kê đơn hàng theo điều kiện và phân trang.
- **WatchOrderUpdates**: theo dõi các cập nhật.
- **UploadReadings**: gửi nhiều bản ghi đo.
- **SynchronizeInventory**: đồng bộ dữ liệu hai chiều.

Tránh tên chỉ mô tả kỹ thuật như **Call**, **Execute**, **ProcessData** hoặc **SendMessage** nếu chúng không cho biết mục đích nghiệp vụ.

## 3. Đặt tên theo ngữ nghĩa, không chỉ theo thao tác CRUD

CRUD là điểm khởi đầu hữu ích, nhưng không phải mọi RPC đều là CRUD. Tên nên trả lời **client muốn đạt được điều gì**:

| Tên mơ hồ | Tên rõ hơn | Lý do |
| --- | --- | --- |
| **Process** | **CalculateShippingFee** | Nêu rõ kết quả nghiệp vụ |
| **GetData** | **GetCustomerProfile** | Chỉ rõ loại dữ liệu |
| **Update** | **ChangeDeliveryAddress** | Nêu rõ điều gì được thay đổi |
| **Send** | **UploadReadings** | Nêu rõ dữ liệu được gửi lên |
| **Stream** | **WatchOrderUpdates** | Nêu rõ nội dung client theo dõi |
| **DoAction** | **ApprovePayment** | Nêu rõ hành động và đối tượng |

Không cần nhồi mọi chi tiết vào tên. **GetProductByIdAndWarehouseCode** thường dài không cần thiết nếu request đã có **product_id** và **warehouse_id**. Tên method nói mục đích; request message mô tả tham số.

### Chọn động từ có nghĩa ổn định

- Dùng **Get** cho truy vấn một tài nguyên hoặc một kết quả cụ thể.
- Dùng **List** cho tập kết quả có thể lọc/phân trang và trả trong một response.
- Dùng **Watch** hoặc **Subscribe** khi client đăng ký nhận cập nhật theo thời gian.
- Dùng **Create** khi tạo tài nguyên mới; dùng **Update** khi thay đổi trạng thái/tài nguyên đã có.
- Dùng **Delete** hoặc **Remove** nhất quán theo ngữ nghĩa domain; không luân phiên hai từ cho cùng một hành vi.
- Dùng **Upload** khi client gửi dữ liệu lên server; dùng **Download** khi client nhận dữ liệu từ server, nhưng vẫn khai báo cardinality rõ trong .proto.

Tên **List** không mặc nhiên có nghĩa server streaming. Một **ListProducts** unary có thể trả **repeated Product** hoặc một trang kết quả. Nếu cần phát từng kết quả theo thời gian, khai báo response stream và chọn tên như **Watch...** hoặc **Stream...** sao cho đúng ngữ nghĩa.

## 4. Request và response message phải tự mô tả

Tên **Request** và **Response** chung chung có thể dùng trong ví dụ rất nhỏ, nhưng trong contract thực tế nên gắn với method:

~~~proto
rpc ReserveStock(ReserveStockRequest)
    returns (ReserveStockResponse);

message ReserveStockRequest {
  string product_id = 1;
  int32 requested_quantity = 2;
  string idempotency_key = 3;
}

message ReserveStockResponse {
  string reservation_id = 1;
  int32 reserved_quantity = 2;
}
~~~

Người đọc có thể nhận ra ngay đầu vào là sản phẩm, số lượng và khóa chống lặp; kết quả là mã đặt giữ và số lượng đã giữ. Nếu dùng **Request** và **Response** cho mọi method, IDE và log có thể xuất hiện nhiều kiểu cùng tên nhưng ý nghĩa khác nhau, gây khó đọc và khó tìm.

### Khi nào nên dùng message dùng chung?

Dùng chung một message khi các method thực sự chia sẻ **cùng ngữ nghĩa và vòng đời dữ liệu**, ví dụ **PageRequest** hoặc **Money**. Không tái sử dụng chỉ để giảm số dòng .proto. Hai request có thể cùng chứa **id** nhưng một request là truy vấn, request kia là lệnh cập nhật; chúng có thể cần validation, quyền và quy tắc tương thích khác nhau.

Với streaming, tên message cần làm rõ từng phần tử mang nghĩa gì:

~~~proto
rpc UploadReadings(stream ReadingChunk)
    returns (UploadReport);

rpc WatchOrderUpdates(WatchOrderUpdatesRequest)
    returns (stream OrderUpdate);

rpc SynchronizeInventory(stream InventoryChange)
    returns (stream SyncResult);
~~~

**ReadingChunk**, **OrderUpdate** và **InventoryChange** diễn tả dữ liệu của từng message. Không nên đặt tên chung **Data** cho mọi loại message streaming, vì người đọc không biết mỗi phần tử là chunk, event, lệnh hay kết quả.

## 5. Đọc contract hoàn chỉnh qua một ví dụ

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.acme.inventory.v1";
option java_multiple_files = true;

service InventoryService {
  // Đọc thông tin một sản phẩm.
  rpc GetProduct(GetProductRequest) returns (Product);

  // Liệt kê một trang sản phẩm.
  rpc ListProducts(ListProductsRequest) returns (ListProductsResponse);

  // Theo dõi các thay đổi tồn kho.
  rpc WatchStock(WatchStockRequest) returns (stream StockUpdate);

  // Gửi nhiều thay đổi và nhận báo cáo tổng hợp.
  rpc UploadStockChanges(stream StockChange)
      returns (UploadStockReport);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int64 available_quantity = 3;
}

message ListProductsRequest {
  int32 page_size = 1;
  string page_token = 2;
}

message ListProductsResponse {
  repeated Product products = 1;
  string next_page_token = 2;
}

message WatchStockRequest {
  string warehouse_id = 1;
}

message StockUpdate {
  string product_id = 1;
  int64 available_quantity = 2;
  int64 version = 3;
}

message StockChange {
  string product_id = 1;
  int64 delta = 2;
  string change_id = 3;
}

message UploadStockReport {
  int64 accepted_count = 1;
  int64 rejected_count = 2;
}
~~~

Khi đọc từ trên xuống, contract cho biết:

1. **Package acme.inventory.v1** xác định namespace và phiên bản API.
2. **InventoryService** chịu trách nhiệm về năng lực tồn kho.
3. **GetProduct** và **ListProducts** là unary; **ListProductsResponse** có **repeated Product** nhưng vẫn chỉ là một response message.
4. **WatchStock** là server streaming vì response có **stream**; client gửi một điều kiện đăng ký và nhận các **StockUpdate** theo thời gian.
5. **UploadStockChanges** là client streaming; client gửi nhiều thay đổi và nhận một **UploadStockReport** cuối cùng.

Tên và kiểu message phối hợp để giải thích luồng dữ liệu. Người đọc không phải xem implementation Java mới biết method nào nhận nhiều message.

## 6. Tên method ảnh hưởng đến đường dẫn RPC và mã Java

Tên method không chỉ xuất hiện trong tài liệu. Với package và service ở ví dụ trên, đường dẫn RPC của **GetProduct** là:

~~~text
/acme.inventory.v1.InventoryService/GetProduct
~~~

Tên package, service và method tham gia xác định **full method name**. Client và server phải thống nhất tên này để định tuyến lời gọi. Đổi package hoặc đổi tên service/method sau khi phát hành có thể làm thay đổi đường dẫn RPC và khiến client cũ không gọi được endpoint cũ.

Mã Java sinh ra thường chuyển tên RPC PascalCase thành method lowerCamelCase trên stub:

| Tên trong .proto | Tên gọi Java thường thấy |
| --- | --- |
| **GetProduct** | **getProduct(...)** |
| **ListProducts** | **listProducts(...)** |
| **WatchStock** | **watchStock(...)** |
| **UploadStockChanges** | **uploadStockChanges(...)** |

Các lớp message vẫn theo PascalCase, ví dụ **GetProductRequest** và **UploadStockReport**. **java_package** điều khiển package của mã Java; nó không thay thế namespace Protobuf dùng trong full method name.

Do đó, cần xem tên RPC là một phần của API đã công bố. Nếu muốn đổi tên, cần cân nhắc giữ method cũ trong giai đoạn chuyển đổi, phát hành method mới, cập nhật client và chỉ loại bỏ method cũ theo chính sách tương thích.

## 7. Các quy tắc giúp contract dễ đọc và dễ phát triển

### Dùng từ nhất quán

Nếu cùng một nghiệp vụ dùng **CancelOrder**, đừng tạo thêm **AbortOrder** hoặc **StopOrder** cho cùng ý nghĩa ở service khác mà không có khác biệt rõ. Từ vựng nhất quán giúp người dùng học API nhanh và tìm method dễ hơn.

### Đặt tên thể hiện đơn vị nghiệp vụ

**UpdateStatus** quá chung chung nếu hệ thống có trạng thái đơn hàng, thanh toán và giao hàng. **UpdateOrderStatus** nói rõ đối tượng. Nếu một method cập nhật nhiều khía cạnh của tài nguyên, **UpdateOrder** có thể hợp lý hơn, miễn request và mô tả làm rõ phạm vi.

### Tránh nhúng chi tiết triển khai

Không đặt tên method theo công nghệ nội bộ như **CallRedis**, **ExecuteSql** hoặc **SendKafka**. Contract nên mô tả hành vi mà client được phép yêu cầu; server có thể thay đổi cơ sở dữ liệu hoặc message broker mà không buộc client đổi tên method.

### Dùng comment cho điều kiện không thể hiện trong tên

Tên **ReserveStock** chưa nói rõ reservation có hết hạn hay có cho phép số lượng một phần. Dùng comment Protobuf và mô tả field để làm rõ quy tắc, đơn vị, giới hạn và lỗi có thể xảy ra. Không biến tên method thành một câu mô tả dài.

### Giữ số field ổn định

Đổi tên method ảnh hưởng full method path; đổi tên field có thể ảnh hưởng mã nguồn và JSON mapping; đổi số field có thể phá vỡ wire compatibility. Khi xóa field, dùng **reserved** cho số và tên đã ngừng sử dụng. Không tái sử dụng số field cũ cho ý nghĩa khác.

## 8. Những tên khó đọc và cách cải thiện

| Contract khó đọc | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| **Process(Request) returns (Response)** | Không biết xử lý việc gì | **CalculateInvoice(InvoiceRequest) returns (Invoice)** |
| **GetAll(Empty) returns (stream Data)** | Không rõ loại dữ liệu, điều kiện và ý nghĩa stream | **WatchOrderUpdates(WatchOrderUpdatesRequest) returns (stream OrderUpdate)** nếu là luồng event |
| **Send(stream Data) returns (Result)** | Không rõ dữ liệu gửi lên và kết quả tổng hợp | **UploadReadings(stream Reading) returns (UploadReport)** |
| **Update(UpdateRequest) returns (UpdateResponse)** | Message không chỉ ra tài nguyên | **UpdateCustomerAddress(UpdateCustomerAddressRequest) returns (Customer)** |
| **DoSync(stream A) returns (stream B)** | Không rõ đối tượng và kết quả | **SynchronizeInventory(stream InventoryChange) returns (stream SyncResult)** |

Không phải cứ tên dài là tốt. Tên tốt là tên **ngắn vừa đủ, cụ thể, nhất quán và đúng ngữ nghĩa**. Hãy để message và comment diễn tả chi tiết đầu vào/đầu ra thay vì dồn mọi thứ vào method name.

## 9. Checklist review contract

Trước khi đưa .proto vào sử dụng, review các câu hỏi:

- Service name có thể hiện đúng domain/năng lực chịu trách nhiệm không?
- Method name có dùng động từ rõ ràng và nói đúng hành vi nghiệp vụ không?
- Request/response message có tên cụ thể, tự mô tả và không tái sử dụng sai ngữ nghĩa không?
- Người đọc có thể nhận ra loại dữ liệu mỗi message chứa không?
- Từ khóa **stream** đã đặt đúng chiều theo nhu cầu chưa?
- Trường **repeated** có bị nhầm với streaming message không?
- Package có namespace và phiên bản phù hợp không?
- Comment có giải thích điều kiện, đơn vị, giới hạn hoặc quy tắc đặc biệt không?
- Việc đổi tên có làm thay đổi full method path hoặc phá client hiện có không?
- Field number đã ổn định và các field xóa có được reserved không?

## 10. Ghi nhớ và tự kiểm tra

Một contract dễ đọc thể hiện rõ ba lớp thông tin: **service** cho biết năng lực, **method** cho biết hành động, còn **request/response message** cho biết dữ liệu đi vào và đi ra. Từ khóa **stream** xác định cardinality của từng chiều; tên method không thể thay thế khai báo này.

Tự kiểm tra:

1. Vì sao **ListProducts** có thể là unary dù response chứa trường **repeated Product**?
2. Tên **UploadReadings** cùng **stream Reading** gợi ý điều gì về chiều dữ liệu?
3. Vì sao đổi **InventoryService.GetProduct** có thể ảnh hưởng client đã phát hành?
4. Khi nào nên dùng message dùng chung, và khi nào nên tạo **Request/Response** riêng cho method?
5. Nếu chỉ nhìn tên **Process**, người đọc còn thiếu thông tin gì để hiểu contract?

Đặt tên tốt không thay thế thiết kế schema, nhưng giúp schema tự giải thích và giảm chi phí tích hợp. Trong Spring gRPC, contract rõ ràng giúp mã Java sinh ra dễ đọc, client chọn đúng stub và các nhóm phát triển phối hợp mà không phải suy đoán ý nghĩa method.
