# Không làm interceptor chứa nghiệp vụ

Interceptor trong Spring gRPC nằm ở ranh giới transport: nó quan sát một RPC trước khi request tới service hoặc khi response/status đi ra. Vị trí này phù hợp cho các concern xuyên suốt như metadata, tracing, authentication, logging, metrics và chính sách chung theo method. Nó không phải nơi triển khai quy tắc của từng use case.

Nếu interceptor tự truy vấn sản phẩm, kiểm tra tồn kho, tính phí, quyết định trạng thái đơn hàng hoặc cập nhật database, transport layer sẽ biết quá nhiều về domain. Khi đó một thay đổi nghiệp vụ có thể buộc sửa interceptor dùng chung, các RPC không liên quan bị ảnh hưởng và logic khó kiểm thử độc lập. **Giữ interceptor mỏng; đặt quyết định nghiệp vụ trong application/domain layer.**

## 1. Phân biệt concern xuyên suốt và quy tắc nghiệp vụ

Một cách phân loại thực tế:

| Concern | Ví dụ | Vị trí phù hợp |
| --- | --- | --- |
| Transport metadata | Đọc/gắn correlation ID, trace context | Client/server interceptor |
| Observability | Ghi method, status, duration, trace attributes | Interceptor hoặc instrumentation |
| Authentication | Xác minh bearer token, tạo principal | Security interceptor/filter hoặc security layer |
| Coarse-grained method policy | Caller có được gọi nhóm RPC quản trị không | Interceptor hoặc method security |
| Resource authorization | Caller có được đọc đúng product/order/tenant này không | Application service/domain policy |
| Input validation | ID không rỗng, format hợp lệ | Adapter/validator và application boundary |
| Business invariant | Không bán sản phẩm đã ngừng kinh doanh; không xuất kho âm | Domain model/domain service |
| Use-case orchestration | Đọc aggregate, kiểm tra quyền, lưu thay đổi, phát event | Application service |
| Persistence | Truy vấn và ghi database | Repository/infrastructure |

Ranh giới không chỉ phụ thuộc tên thao tác. Authentication xác định caller là ai; authorization theo tài nguyên cần biết caller muốn làm gì với đối tượng nào. Interceptor thường biết method name và metadata nhưng không nên phải tải domain object chỉ để quyết định một quy tắc riêng của use case.

## 2. Anti-pattern: interceptor truy vấn và quyết định nghiệp vụ

Ví dụ không nên dùng:

```java
public final class ProductPolicyInterceptor implements ServerInterceptor {
    private final ProductRepository products;

    public ProductPolicyInterceptor(ProductRepository products) {
        this.products = products;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String productId = headers.get(PRODUCT_ID);
        Product product = products.findById(productId).orElse(null);

        if (product == null || product.isDiscontinued()) {
            call.close(Status.FAILED_PRECONDITION, new Metadata());
            return new ServerCall.Listener<>() {};
        }
        return next.startCall(call, headers);
    }
}
```

Đoạn code này tạo nhiều vấn đề:

- Interceptor phụ thuộc repository và cấu trúc domain của Product.
- Nó giả định mọi RPC đi qua interceptor đều thao tác trên cùng một sản phẩm.
- product_id bị đưa vào metadata dù có thể vốn là dữ liệu nghiệp vụ trong protobuf request.
- Quyết định sản phẩm có được bán hay không có thể khác nhau giữa GetProduct, ReserveStock và AdminUpdateProduct.
- Database lookup chạy trên đường xử lý transport; độ trễ, timeout và lỗi persistence ảnh hưởng trực tiếp việc mở RPC.
- Quy tắc bị giấu ngoài application service, khiến một đường gọi khác có thể bỏ qua nó.

Đặc biệt, interceptCall nhận metadata và descriptor trước khi nhận request message. Với unary hoặc streaming, interceptor không thể dựa vào request body theo cách handler xử lý; việc chuyển dữ liệu nghiệp vụ qua metadata để interceptor đọc là dấu hiệu thiết kế sai ranh giới.

## 3. Interceptor nên làm gì?

Một server interceptor tốt thường có một trách nhiệm kỹ thuật rõ ràng:

```java
public final class RequestContextInterceptor implements ServerInterceptor {
    static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID_METADATA);
        if (requestId == null || requestId.isBlank()) {
            requestId = java.util.UUID.randomUUID().toString();
        }

        Context context = Context.current().withValue(REQUEST_ID, requestId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Interceptor này đọc metadata, tạo ID kỹ thuật khi thiếu và gắn nó vào gRPC Context. Nó không cần biết Product, Order, bảng database hay chính sách giá. Service có thể lấy request ID để ghi log; application service vẫn nhận input nghiệp vụ theo use case.

Các concern phù hợp khác:

- Authentication interceptor xác minh credential và đưa principal đã xác thực vào Context.
- Metrics interceptor ghi method, RPC type, status và duration với tag cardinality hữu hạn.
- Tracing instrumentation inject/extract W3C trace context và quản lý span lifecycle.
- Exception boundary chuyển exception đồng bộ sang gRPC status theo mapper tập trung.

Các concern này có tính xuyên suốt nhiều RPC và có thể mô tả độc lập với một use case cụ thể.

## 4. Resource authorization thuộc application boundary

Interceptor có thể xác thực caller hoặc chặn một nhóm method theo policy chung. Nhưng khi quyết định phụ thuộc vào tài nguyên trong request, application service thường có đủ ngữ cảnh hơn.

Endpoint chỉ chuyển protobuf request thành lời gọi use case:

```java
@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final GetProductUseCase getProduct;

    public CatalogGrpcEndpoint(GetProductUseCase getProduct) {
        this.getProduct = getProduct;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {
        ProductView result = getProduct.execute(
                request.getProductId(),
                CurrentPrincipal.require());
        observer.onNext(toResponse(result));
        observer.onCompleted();
    }
}
```

Use case nhận ID và principal, sau đó thực hiện authorization và nghiệp vụ:

```java
public final class GetProductUseCase {
    private final ProductRepository products;
    private final ProductAccessPolicy accessPolicy;

    public GetProductUseCase(
            ProductRepository products,
            ProductAccessPolicy accessPolicy) {
        this.products = products;
        this.accessPolicy = accessPolicy;
    }

    public ProductView execute(
            String productId,
            AuthenticatedPrincipal principal) {
        Product product = products.findById(productId)
                .orElseThrow(ProductNotFoundException::new);

        accessPolicy.checkCanRead(principal, product);
        return ProductView.from(product);
    }
}
```

CurrentPrincipal.require() là adapter minh họa đọc principal từ security context hiện hành. Trong dự án thật, có thể lấy principal ở endpoint rồi truyền rõ ràng vào use case; cách đó làm dependency dễ nhìn và test hơn. Điểm chính là quyền đọc một Product được kiểm tra tại use case/domain policy, nơi đã có cả principal lẫn đối tượng.

## 5. Không chuyển request body thành metadata để né tầng ứng dụng

Metadata dành cho thông tin điều khiển ngắn như authorization, trace context, deadline liên quan transport và correlation ID. Dữ liệu use case phải ở protobuf request:

```proto
message ReserveStockRequest {
  string product_id = 1;
  int32 quantity = 2;
  string warehouse_id = 3;
}
```

quantity, product_id và warehouse_id là input nghiệp vụ. Interceptor không nên yêu cầu client lặp các field này trong metadata. Làm vậy tạo hai nguồn dữ liệu có thể mâu thuẫn và khiến contract khó hiểu.

Validation có thể được chia theo tầng:

- Adapter kiểm tra điều kiện hình thức đơn giản, ví dụ field bắt buộc hoặc định dạng.
- Application service xác thực input theo use case và quyền truy cập.
- Domain model bảo vệ invariant không được vi phạm, bất kể use case được gọi từ gRPC, REST, message consumer hay batch.

Không đặt invariant chỉ ở interceptor vì domain có thể được gọi từ nhiều entry point.

## 6. Interceptor không nên điều phối transaction hoặc workflow

Không mở transaction, gọi nhiều repository, phát domain event hay điều phối saga trong interceptor. Những công việc đó thuộc application service và cần ranh giới transaction rõ ràng.

Nếu interceptor cập nhật last_accessed_at của entity mỗi lần RPC, nó biến một concern quan sát thành side effect nghiệp vụ. Side effect này có thể:

- Chạy cả với health check hoặc RPC bị từ chối.
- Tạo ghi database cho mọi call và làm tăng tải.
- Không có cùng semantics với thao tác đọc/ghi của use case.
- Khó rollback hoặc phối hợp với transaction của handler.

Nếu thật sự cần audit một hành động nghiệp vụ, application service nên phát audit event sau khi xác định hành động hợp lệ và kết quả. Nếu chỉ cần access log kỹ thuật, interceptor ghi log/metric mà không sửa domain state.

## 7. Giữ interceptor an toàn khi chạy đồng thời

Interceptor thường được đăng ký dùng chung cho nhiều RPC. Vì vậy:

- Không lưu principal, product, request ID hoặc trạng thái từng call vào field mutable của singleton.
- Tạo state per-call bên trong interceptCall nếu cần đếm message hoặc bảo đảm close một lần.
- Dùng gRPC Context cho dữ liệu gắn với call; truyền context tường minh qua executor khi xử lý bất đồng bộ.
- Không thực hiện database/network I/O blocking trong callback transport.
- Không giữ reference tới request/response sau khi call kết thúc.
- Không để lỗi ghi log/metrics làm thay đổi kết quả RPC.

Những nguyên tắc này giữ interceptor mỏng, dự đoán được và không tạo race giữa các request đồng thời.

## 8. Đăng ký và phân tầng trong Spring gRPC

Một cách tổ chức đơn giản:

```text
gRPC transport
  -> Interceptors
       metadata / tracing / authentication / metrics
  -> gRPC endpoint adapter
       protobuf <-> application input/output
  -> Application use case
       authorization theo tài nguyên / orchestration
  -> Domain
       invariant / business rules
  -> Repository and infrastructure
       database / remote systems
```

Trong Spring gRPC, endpoint và server thường được framework auto-configure. Đăng ký interceptor qua extension point của đúng phiên bản đang dùng; không mặc định một bean bất kỳ tự động trở thành interceptor. Giữ dependency theo hướng một chiều: interceptor không phụ thuộc use case/repository; endpoint gọi application service; domain không phụ thuộc gRPC hoặc generated protobuf classes.

Nếu cần policy chung theo method, có thể dùng full method name trong interceptor và một policy cấu hình nhỏ. Policy đó không nên tải entity hoặc chứa nhánh xử lý cho từng loại sản phẩm/đơn hàng. Khi quyết định cần dữ liệu domain, chuyển nó vào application/domain layer.

## 9. Kiểm thử để phát hiện nghiệp vụ bị đặt sai tầng

Một bộ test tốt kiểm tra cả interceptor lẫn use case:

| Test | Điều cần chứng minh |
| --- | --- |
| Interceptor unit test | Metadata/context/status kỹ thuật được xử lý đúng, không gọi repository |
| Use-case unit test | Authorization theo tài nguyên và business invariant được áp dụng |
| Endpoint integration test | Protobuf request được chuyển thành input đúng; lỗi use case được ánh xạ thành status |
| Alternate entry point test | Cùng use case vẫn bảo vệ invariant khi được gọi ngoài gRPC |
| Concurrency test | Context/principal của hai RPC không bị trộn |
| Failure test | Lỗi database/domain không làm interceptor giữ call hoặc đóng call hai lần |

Ví dụ, test interceptor có thể inject một repository giả và xác minh nó không bao giờ được gọi; tốt hơn nữa, thiết kế interceptor không có dependency repository ngay từ đầu. Test use case cần bao phủ caller thuộc tenant khác, sản phẩm ngừng kinh doanh và tài nguyên không tồn tại.

## 10. Checklist review interceptor

- [ ] Interceptor có một trách nhiệm kỹ thuật xuyên suốt và mô tả được trong một câu.
- [ ] Không truy vấn hoặc cập nhật entity/repository.
- [ ] Không tính giá, kiểm tra tồn kho hay quyết định trạng thái nghiệp vụ.
- [ ] Không yêu cầu client gửi dữ liệu use case qua metadata.
- [ ] Authentication được tách khỏi authorization theo tài nguyên.
- [ ] Quy tắc nghiệp vụ nằm trong application/domain layer và áp dụng cho mọi entry point.
- [ ] Interceptor không giữ mutable state per-call trong field dùng chung.
- [ ] Không thực hiện I/O blocking hoặc workflow trong callback transport.
- [ ] Log/metrics/tracing không làm thay đổi kết quả RPC.
- [ ] Có unit test cho interceptor và use-case test cho nghiệp vụ.

**Tự kiểm tra**

**Câu 1.** Interceptor có nên truy vấn ProductRepository để chặn sản phẩm ngừng kinh doanh không?

*Đáp án:* Không. Đây là quy tắc phụ thuộc domain và use case. Application/domain service cần kiểm tra trạng thái sản phẩm để mọi entry point đều áp dụng cùng invariant.

**Câu 2.** Interceptor có thể xác thực bearer token không?

*Đáp án:* Có. Xác minh credential là concern xuyên suốt tại ranh giới RPC. Sau đó interceptor đưa principal đã xác thực vào Context; quyền trên tài nguyên cụ thể vẫn được kiểm tra ở application layer.

**Câu 3.** Vì sao không đưa quantity và product_id vào metadata?

*Đáp án:* Đây là dữ liệu nghiệp vụ thuộc protobuf request. Metadata dành cho thông tin điều khiển; đưa cùng dữ liệu vào hai nơi tạo nguồn dữ liệu mâu thuẫn.

**Câu 4.** Vì sao invariant không nên chỉ được kiểm tra trong interceptor?

*Đáp án:* Use case/domain có thể được gọi từ REST, message consumer, batch hoặc test. Đặt invariant trong domain/application bảo vệ mọi entry point.

**Câu 5.** Interceptor singleton cần tránh điều gì khi có nhiều RPC đồng thời?

*Đáp án:* Không lưu state riêng của call vào field mutable dùng chung. Dùng biến cục bộ trong interceptCall, gRPC Context và cơ chế truyền context qua executor.

Interceptor tốt giữ ranh giới transport rõ ràng: xử lý metadata, security context và quan sát RPC; application/domain quyết định hành vi nghiệp vụ. Khi không để interceptor truy cập repository hoặc điều phối use case, Spring gRPC dễ kiểm thử hơn, các quy tắc được tái sử dụng và thay đổi domain ít ảnh hưởng tới hạ tầng RPC.
