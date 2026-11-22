# Kiểm thử tích hợp

Trong một hệ thống sử dụng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), các thành phần hiếm khi hoạt động độc lập. Parser tạo cú pháp cho semantic analyzer; semantic analyzer resolve kiểu và tham chiếu; compiler hoặc generator tạo artifact; runtime thực thi artifact; API, database, plugin và hệ thống ngoài cung cấp dữ liệu hoặc dịch vụ. Một thành phần có thể vượt qua unit test nhưng toàn bộ luồng vẫn thất bại do contract giữa hai thành phần không khớp, cấu hình môi trường sai hoặc artifact được sinh ra không tương thích với runtime.

**Kiểm thử tích hợp (integration testing)** xác minh nhiều thành phần phối hợp đúng khi được kết nối qua các interface và môi trường thực tế hoặc gần thực tế. Trong DSL, kiểm thử tích hợp có thể bao phủ đường đi từ source text đến kết quả thực thi, từ khai báo API đến HTTP endpoint, từ schema đến database, hoặc từ plugin manifest đến extension được host gọi.

Mục tiêu là phát hiện lỗi ở ranh giới: dữ liệu truyền giữa các tầng có đúng định dạng không, dependency có được resolve đúng không, transaction có giữ invariant không, generated code có compile và chạy được không, event có được phát và xử lý đúng không, và lỗi từ hệ thống phụ thuộc có được chuyển thành kết quả phù hợp không. Một bộ integration test tốt tạo bằng chứng rằng các thành phần thật sự làm việc cùng nhau theo contract đã công bố.

## 1. Kiểm thử tích hợp là gì?

Unit test thường kiểm tra một hàm hoặc một đơn vị nhỏ trong isolation. Integration test kiểm tra tương tác giữa hai hay nhiều thành phần có contract cụ thể.

Ví dụ trong DSL compiler:

1. Đọc file DSL.
2. Parse thành syntax tree.
3. Resolve symbol và type.
4. Tạo intermediate representation.
5. Generate Java source.
6. Compile source.
7. Nạp artifact vào runtime.
8. Thực thi và kiểm tra kết quả.

Một test chỉ gọi parser và kiểm tra AST là unit hoặc component test. Một test chạy từ DSL source qua generator, compiler và runtime xác minh nhiều ranh giới nên là integration test.

Ví dụ khác: API DSL sinh endpoint cho CreateOrder. Integration test có thể khởi động HTTP server, gửi JSON request, xác thực input, gọi service, ghi database và kiểm tra response cùng trạng thái lưu trữ.

Integration test không nhất thiết phải kết nối mọi hệ thống production. Mục đích là kiểm tra các contract quan trọng với mức độ chân thực phù hợp. Một số dependency có thể dùng database thật trong container; một số dịch vụ bên ngoài có thể dùng test server hoặc contract stub.

## 2. Vì sao DSL cần kiểm thử tích hợp?

DSL thường có nhiều tầng và có thể sinh ra code hoặc cấu hình được hệ thống khác tiêu thụ. Lỗi có thể không nằm trong một hàm riêng lẻ mà xuất hiện khi các tầng kết hợp.

Các ví dụ:

- Parser chấp nhận syntax nhưng AST builder bỏ mất annotation.
- Type checker resolve đúng symbol nhưng generator dùng tên đã bị normalize sai.
- Generator tạo Java source hợp lệ về cú pháp nhưng thiếu dependency runtime.
- Schema generator tạo OpenAPI khác với behavior của HTTP handler.
- Plugin đăng ký thành công nhưng host truyền context không đúng version.
- Migration SQL chạy được trên database rỗng nhưng thất bại khi nâng cấp dữ liệu thật.
- Event publisher gửi payload có field khác với consumer schema.
- Cache trả artifact cũ sau khi một dependency DSL thay đổi.

Kiểm thử tích hợp giúp phát hiện:
- Contract mismatch.
- Cấu hình và wiring sai.
- Dependency resolution sai.
- Serialization/deserialization không tương thích.
- Transaction và persistence issue.
- Lifecycle và ordering bug.
- Sai khác giữa generated artifact và runtime.
- Lỗi retry, timeout, cancellation và resource cleanup.
- Khác biệt giữa môi trường local, CI và production.

## 3. Ranh giới tích hợp trong một hệ thống DSL

Trước khi viết test, cần xác định các ranh giới có nguy cơ cao.

~~~mermaid
flowchart TD
    A[DSL source] --> B[Parser]
    B --> C[Semantic analyzer]
    C --> D[Intermediate representation]
    D --> E[Generator]
    E --> F[Build and package]
    F --> G[Runtime]
    G --> H[API and application services]
    H --> I[Database and external systems]
    E --> J[Generated metadata]
    J --> K[IDE and tooling]
~~~

Các ranh giới thường gặp:

| Ranh giới | Điều cần xác minh |
|---|---|
| Source → Parser | Encoding, syntax, source locations |
| Parser → Semantic analyzer | AST shape, node identity, annotations |
| Analyzer → Generator | Type, symbol, dependency metadata |
| Generator → Build | Output path, source set, resource registration |
| Build → Runtime | Dependency và version compatibility |
| DSL API → HTTP framework | Route, binding, validation, error mapping |
| Domain model → Database | Mapping, schema, transaction và constraint |
| Plugin → Host | Extension contract, lifecycle và permissions |
| Event producer → Consumer | Schema, ordering, delivery và idempotency |
| CLI → Deployment provider | Credentials, target, result và audit |

Không cần một test khổng lồ cho mọi thứ. Có thể viết test theo từng boundary và một số end-to-end flow đại diện.

## 4. Phân biệt unit, component, integration và end-to-end test

Các loại test có phạm vi khác nhau:

| Loại test | Phạm vi | Dependency |
|---|---|---|
| Unit test | Hàm hoặc class nhỏ | Thường fake/mock |
| Component test | Một thành phần với interface của nó | Có thể dùng dependency thật cục bộ |
| Integration test | Nhiều thành phần được kết nối | Một phần hạ tầng thật hoặc test implementation |
| End-to-end test | Luồng nghiệp vụ qua hệ thống gần hoàn chỉnh | Nhiều dịch vụ thật trong test environment |
| Contract test | Một phía xác minh thỏa contract | Provider hoặc consumer được kiểm tra riêng |

Ví dụ:
- Unit test kiểm tra hàm tính biểu thức.
- Component test kiểm tra parser và AST factory.
- Integration test kiểm tra parser, analyzer và generator.
- End-to-end test gửi request qua API, ghi database và đọc kết quả.
- Contract test xác minh OpenAPI client và server đồng thuận về request/response.

Các loại test bổ sung cho nhau. Integration test không thay thế unit test vì test rộng thường khó định vị lỗi. Unit test cũng không thay thế integration test vì mock có thể che giấu contract mismatch.

## 5. Chọn phạm vi integration test

Một integration test nên có mục tiêu cụ thể. Ví dụ:

- DSL source được parse và resolve qua module import.
- Generated Java code compile với runtime API hiện hành.
- Endpoint được sinh ra xử lý request hợp lệ và lỗi validation.
- Repository lưu và tải lại aggregate đúng semantics.
- Plugin được discover, load, register và invoke.
- Event được publish, serialize, consume và deduplicate.
- Build task nhận generated source như một input đúng.

Nên chọn phạm vi theo ranh giới có rủi ro, tần suất thay đổi và mức độ ảnh hưởng khi lỗi. Một test không cần boot toàn bộ hệ thống nếu chỉ cần xác minh generator output và compiler integration.

## 6. Thiết kế test fixture cho DSL

Test fixture là source, model, configuration hoặc dữ liệu được dùng để thiết lập test.

Một cấu trúc có thể là:

~~~text
src/test/resources/integration/
  parser/
    valid-imports.dsl
    invalid-reference.dsl
  generation/
    order-model.dsl
    expected/
      Order.java
      OrderRepository.java
  api/
    create-order.dsl
    requests/
      valid-order.json
      invalid-order.json
  database/
    schema.dsl
    migrations/
      V1__initial.sql
  plugins/
    sample-plugin/
      plugin.yml
~~~

Fixture cần:
- Nhỏ và tập trung vào một behavior.
- Có tên mô tả ý nghĩa.
- Dễ đọc và dễ cập nhật.
- Không phụ thuộc path tuyệt đối trên máy.
- Không chứa credential thật hoặc dữ liệu nhạy cảm.
- Có expected result hoặc assertion rõ.
- Được version cùng test để thay đổi có review.

Không nên dùng một fixture khổng lồ cho mọi test. Khi một fixture chứa nhiều tính năng, lỗi có thể khó định vị và thay đổi nhỏ dễ làm nhiều test thất bại không liên quan.

## 7. Test harness và môi trường tích hợp

Test harness chuẩn bị thành phần cần thiết, chạy test và dọn dẹp tài nguyên. Nó có thể:
- Khởi động ứng dụng hoặc embedded server.
- Tạo database/schema riêng.
- Nạp DSL source và plugin.
- Cấu hình clock, locale và environment.
- Cung cấp test credentials.
- Ghi log và artifact khi thất bại.
- Dừng process và xóa resource sau test.

Một harness Java có thể dùng JUnit extension hoặc test fixture object:

~~~java
final class DslIntegrationEnvironment implements AutoCloseable {
    private final TestDatabase database;
    private final DslRuntime runtime;
    private final HttpTestServer server;

    DslIntegrationEnvironment() {
        database = TestDatabase.start();
        runtime = DslRuntime.create(database.connectionInfo());
        server = HttpTestServer.start(runtime);
    }

    URI baseUri() {
        return server.baseUri();
    }

    @Override
    public void close() {
        server.close();
        runtime.close();
        database.close();
    }
}
~~~

Đây là ví dụ khái niệm. Implementation nên đảm bảo cleanup cả khi constructor hoặc test thất bại giữa chừng. Tài nguyên cần được đóng theo thứ tự ngược với thứ tự khởi tạo.

## 8. Kiểm thử đường đi từ DSL source đến runtime

Một flow quan trọng là kiểm tra source DSL tạo ra hành vi runtime mong đợi.

Ví dụ DSL:

~~~text
entity Order {
    id: UUID
    quantity: Integer
    unitPrice: Decimal
}

rule "order.total" {
    when order.quantity > 0
    then order.total = order.quantity * order.unitPrice
}
~~~

Integration test có thể:
1. Nạp source fixture.
2. Parse và kiểm tra diagnostics.
3. Resolve entity và rule.
4. Compile hoặc generate runtime representation.
5. Nạp artifact vào runtime.
6. Tạo input model.
7. Thực thi rule.
8. Assert total và trace.

Ví dụ Java:

~~~java
@Test
void generatedRuleCalculatesOrderTotal() {
    DslProgram program = compiler.compile(
        readFixture("order-total.dsl")
    );

    Order order = new Order(
        UUID.randomUUID(),
        3,
        new BigDecimal("12.50")
    );

    DecisionResult result = runtime.evaluate(
        program,
        "order.total",
        order
    );

    assertEquals(
        new BigDecimal("37.50"),
        order.total()
    );
    assertTrue(result.success());
}
~~~

Test này kiểm tra contract giữa parser, compiler, runtime và domain object. Khi fail, cần log phase và diagnostics để biết lỗi nằm ở đâu.

## 9. Kiểm thử parser và semantic analyzer cùng nhau

Parser có thể tạo AST đúng cấu trúc nhưng semantic analyzer diễn giải sai import, scope hoặc type.

Một integration test có thể sử dụng nhiều file:

~~~text
module catalog {
    entity Product {
        id: UUID
        price: Money
    }
}

module order {
    import catalog.Product

    entity OrderLine {
        product: Product
        quantity: Integer
    }
}
~~~

Test cần xác minh:
- Import được resolve đến đúng module.
- Product reference dùng đúng symbol identity.
- Type của product field được xác định.
- Source location của lỗi được giữ.
- Circular import được phát hiện theo policy.
- Cache/index không dùng symbol từ revision cũ.

Nên có test cho cả success path và failure path. Ví dụ đổi import thành module không tồn tại và xác nhận diagnostic có code, source span và message phù hợp.

## 10. Kiểm thử generator và build integration

Generator không chỉ cần tạo text. Output cần được build system nhận diện và compiler/runtime tiêu thụ được.

Một flow:
1. Nạp DSL model.
2. Chạy generator vào temporary output directory.
3. Kiểm tra artifact manifest.
4. Đăng ký generated source/resource với build model.
5. Compile generated source.
6. Chạy test hoặc runtime smoke test.
7. Xác minh checksum/provenance nếu contract yêu cầu.

Ví dụ:

~~~java
@Test
void generatedJavaCompilesAgainstRuntimeApi() {
    GenerationResult generated =
        generator.generate(loadModel("customer.dsl"));

    assertTrue(generated.success());
    assertTrue(Files.exists(generated.source("Customer.java")));

    CompilationResult compilation =
        javaCompiler.compile(
            generated.sourceFiles(),
            runtimeClasspath()
        );

    assertTrue(compilation.success(), compilation.diagnostics());
}
~~~

Test này phát hiện lỗi mà snapshot text đơn thuần không phát hiện, chẳng hạn import thiếu, kiểu không tương thích hoặc method signature sai.

## 11. Golden file và snapshot test

Golden test so sánh output hiện tại với file kỳ vọng. Nó hữu ích cho generated source, schema, manifest và documentation.

Ví dụ:
- Input: DSL model.
- Actual: OpenAPI document.
- Expected: openapi.expected.yml.

Khi output khác, test báo diff. Golden file nên được cập nhật có chủ đích sau khi review thay đổi.

Không nên chỉ assert toàn bộ file string nếu output có metadata không ổn định như timestamp hoặc absolute path. Có thể normalize phần không quan trọng hoặc parse output thành cấu trúc rồi so sánh semantics.

Golden test cho thấy output thay đổi; nó không chứng minh output chạy được. Nên kết hợp với compile test, schema validation hoặc runtime test.

## 12. Kiểm thử API được sinh từ DSL

Một DSL API có thể sinh route, request model, response model và validation logic. Integration test nên khởi động HTTP server thật trong test process và gửi request qua transport.

Ví dụ:

~~~java
@Test
void createOrderEndpointPersistsOrder() {
    HttpResponse<String> response = client.send(
        HttpRequest.newBuilder(baseUri.resolve("/orders"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("""
                {
                  "customerId": "00000000-0000-0000-0000-000000000001",
                  "items": [
                    {"productId": "00000000-0000-0000-0000-000000000002",
                     "quantity": 2}
                  ]
                }
                """))
            .build(),
        HttpResponse.BodyHandlers.ofString()
    );

    assertEquals(201, response.statusCode());
    assertEquals(1, orderRepository.count());
}
~~~

Test này xác minh route mapping, JSON binding, validation, service wiring, persistence và response mapping. Nó nên dùng database test riêng và không gọi production service.

Cũng cần kiểm tra request sai:
- Field bắt buộc bị thiếu.
- Type không đúng.
- Unknown field theo policy.
- Collection vượt maxItems.
- Resource không tồn tại.
- Caller thiếu quyền.
- Database conflict.

## 13. Kiểm thử serialization và schema compatibility

DSL có thể sinh JSON Schema, OpenAPI hoặc message schema. Cần xác minh serializer và deserializer dùng cùng semantics.

Các trường hợp quan trọng:
- Required và optional.
- Nullable.
- Default value.
- Enum value.
- Decimal precision.
- Date/time và timezone.
- Nested object.
- Unknown field.
- Version discriminator.
- Polymorphic payload.

Một test có thể:
1. Sinh schema từ DSL.
2. Validate fixture hợp lệ bằng schema.
3. Validate fixture không hợp lệ và kiểm tra lỗi.
4. Serialize object runtime.
5. Deserialize lại.
6. So sánh semantics của object.

Không nên chỉ kiểm tra schema file tồn tại. Schema cần được parser/validator độc lập chấp nhận và phải phản ánh đúng runtime contract.

## 14. Kiểm thử database integration

Nếu DSL mô tả entity, query, migration hoặc repository, database integration test giúp xác minh mapping và semantics thực tế.

Các vấn đề thường gặp:
- Column type mapping.
- Nullability.
- Primary/foreign key.
- Unique/check constraint.
- Decimal precision.
- Date/time timezone.
- Index và query plan.
- Transaction rollback.
- Locking và concurrent update.
- Migration từ schema cũ.

Có thể dùng database thật trong container để tránh khác biệt giữa embedded database và production engine. Nếu chỉ dùng in-memory database, cần hiểu rõ các tính năng không tương thích.

Test nên tạo database/schema riêng hoặc namespace riêng. Không dùng chung database developer hay production.

## 15. Migration integration test

Migration cần kiểm tra cả database mới và database đã có dữ liệu.

Hai luồng cơ bản:

**Fresh install**
1. Tạo database rỗng.
2. Chạy toàn bộ migration.
3. Kiểm tra schema cuối.
4. Seed dữ liệu.
5. Chạy repository hoặc query test.

**Upgrade**
1. Tạo schema ở version cũ.
2. Seed dữ liệu đại diện.
3. Chạy migration tiếp theo.
4. Kiểm tra schema và dữ liệu sau migration.
5. Kiểm tra rollback hoặc recovery nếu hệ thống hỗ trợ.

Ví dụ kiểm tra:

~~~sql
SELECT version
FROM schema_migrations
ORDER BY version;
~~~

Migration test nên xác minh dữ liệu cũ không bị mất hoặc chuyển sai. Chỉ kiểm tra migration command trả exit code 0 là chưa đủ.

## 16. Transaction và concurrency

Một integration test có thể cần xác minh nhiều thao tác trong transaction:

- Tạo parent và child cùng transaction.
- Rollback khi một bước thất bại.
- Unique constraint khi hai request đồng thời.
- Optimistic locking khi hai client cập nhật cùng resource.
- Isolation level và visibility.
- Idempotency của command.

Ví dụ hai request cùng tạo một username. Cả hai có thể vượt qua validation “username chưa tồn tại” nếu kiểm tra diễn ra trước insert. Database unique constraint cần đảm bảo chỉ một request thành công.

Concurrency test cần đồng bộ hóa thread/barrier thay vì dùng sleep để đoán timing. Kết quả cần kiểm tra theo invariant, không phụ thuộc thread nào thắng.

## 17. Kiểm thử plugin integration

Plugin system có nhiều ranh giới: manifest, discovery, dependency resolver, classloader/module layer, lifecycle và extension registry.

Một integration test có thể:
1. Đặt plugin package vào test repository.
2. Khởi tạo host plugin manager.
3. Discover manifest.
4. Resolve dependency và compatibility.
5. Load plugin.
6. Invoke extension point.
7. Kiểm tra kết quả.
8. Disable plugin.
9. Xác nhận extension bị unregister và tài nguyên được giải phóng.

Cần có fixture plugin thành công và plugin lỗi:
- Manifest thiếu field.
- Version không tương thích.
- Dependency conflict.
- Duplicate extension ID.
- Initialize ném exception.
- Stop timeout.
- Extension trả output không hợp lệ.

Không nên kiểm tra riêng registry mà bỏ qua discovery và lifecycle nếu mục tiêu là bảo đảm plugin thực sự cài đặt được.

## 18. Kiểm thử event-driven integration

Một DSL có thể sinh event schema hoặc workflow xử lý message. Integration test nên xác minh:
- Event được serialize đúng.
- Producer gửi đúng topic/queue.
- Consumer nhận và deserialize được.
- Schema version tương thích.
- Ordering hoặc partition key đúng.
- Retry và dead-letter behavior.
- Duplicate delivery được xử lý.
- Idempotency giữ invariant.
- Correlation ID được truyền qua các service.

Với broker thật trong container, test có thể xác minh protocol và serialization thực tế. Với test nhanh hơn, embedded broker hoặc test server có thể đủ nếu contract cần kiểm tra không phụ thuộc behavior đặc thù của broker.

Không nên giả định message chỉ được giao một lần. Nhiều hệ thống có at-least-once delivery; consumer cần idempotent hoặc deduplicate theo event ID.

## 19. Kiểm thử external service và test double

Không phải dependency nào cũng nên gọi thật trong mọi test. Các lựa chọn:

- **Fake:** implementation đơn giản có behavior phù hợp cho test.
- **Stub:** trả response định trước.
- **Mock:** xác minh tương tác hoặc lời gọi cụ thể.
- **Simulator:** mô phỏng protocol/state machine.
- **Sandbox service:** môi trường thử nghiệm do nhà cung cấp cung cấp.
- **Real dependency:** dịch vụ thật trong môi trường test được kiểm soát.

Chọn theo câu hỏi cần trả lời. Nếu cần xác minh HTTP serialization, dùng test server thật có thể tốt hơn mock method. Nếu cần xác minh behavior của payment provider, sandbox có thể cần thiết nhưng vẫn không thay thế contract test.

Test double có thể che giấu khác biệt protocol. Nên có một số test contract hoặc sandbox test định kỳ với dependency thật.

## 20. Contract testing giữa consumer và provider

Contract test xác minh hai phía đồng ý về interface. Consumer mô tả request/response hoặc message schema mong đợi; provider chạy test để xác nhận đáp ứng contract.

Trong DSL:
- DSL API generator sinh OpenAPI contract.
- Client generator dùng contract đó.
- Server implementation cần đáp ứng schema.
- Consumer contract test gửi request và kiểm tra response.
- Provider verification chạy cùng contract trên server.

Contract cần bao gồm:
- Method/path/topic.
- Request shape.
- Required/optional/nullability.
- Status code hoặc event outcome.
- Response schema.
- Error model.
- Headers và versioning.
- Behavior quan trọng như idempotency.

Contract test giảm rủi ro integration drift giữa team, nhưng không chứng minh toàn bộ workflow nghiệp vụ đúng.

## 21. Kiểm thử security integration

Security thường phụ thuộc nhiều tầng phối hợp. Test cần xác minh:
- Authentication filter truyền identity đúng.
- Authorization policy được áp dụng cho resource.
- Tenant isolation.
- Generated endpoint không bỏ qua validation.
- SQL query dùng parameter binding.
- Secret được lấy từ provider.
- Plugin chỉ dùng capability được cấp.
- Audit event được ghi cho thao tác nhạy cảm.
- File upload không cho path traversal.
- Error response không tiết lộ nội bộ.

Ví dụ tenant test:
1. Tạo user thuộc tenant A và resource của tenant B.
2. Gửi request từ user A tham chiếu resource B.
3. Xác nhận request bị từ chối theo policy.
4. Xác nhận dữ liệu tenant B không bị trả về.
5. Xác nhận không có side effect ngoài ý muốn.

Security test nên kiểm tra cả response và trạng thái hệ thống sau request.

## 22. Kiểm thử error mapping và failure propagation

Một thành phần có thể phát ra exception riêng. Tầng tích hợp cần chuyển thành error model ổn định.

Ví dụ:
- Parse error → 400 với source location.
- Validation error → 400 hoặc 422 theo API convention.
- Authorization error → 403 hoặc 404 theo policy.
- Optimistic lock conflict → 409.
- Dependency unavailable → 503 hoặc retryable failure.
- Internal bug → 500 với correlation ID, không lộ stack trace.

Integration test nên kích hoạt lỗi thật ở từng boundary và xác minh:
- Status/result.
- Error code.
- Không lộ dữ liệu nhạy cảm.
- Transaction rollback.
- Resource cleanup.
- Retry có hoặc không theo policy.
- Diagnostic được gắn đúng request/task.

Không nên chỉ assert exception type nếu API consumer nhận HTTP response hoặc event result.

## 23. Determinism: clock, random và external facts

Integration test dễ flaky nếu phụ thuộc thời gian hiện tại, random hoặc dữ liệu bên ngoài thay đổi.

Các dependency nên được inject:
- Clock.
- Random seed.
- Locale.
- Timezone.
- Feature flags.
- Exchange rate hoặc reference data.
- External API response.
- Environment configuration.

Ví dụ Java:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2027-01-10T10:00:00Z"),
    ZoneOffset.UTC
);

ApplicationContext context =
    TestApplication.create(fixedClock);
~~~

Với DSL có hàm now(), nên có cách truyền evaluation time để test được thời điểm chính xác. Test boundary trước, tại và sau effective date giúp tránh lỗi timezone và daylight saving.

## 24. Test data và data isolation

Test data cần độc lập giữa test và có thể tái tạo.

Các chiến lược:
- Tạo database/schema riêng cho test.
- Transaction rollback sau mỗi test khi phù hợp.
- Seed fixture qua builder hoặc factory.
- Dùng ID ngẫu nhiên có kiểm soát.
- Dùng namespace theo test run.
- Dọn resource trong finally/close.
- Không phụ thuộc thứ tự test.
- Không dùng shared mutable singleton cho dữ liệu test.

Transaction rollback thuận tiện nhưng không bao phủ mọi side effect như message publish, external HTTP call hoặc sequence behavior. Với các trường hợp đó cần cleanup hoặc test resource riêng.

Test parallel cần có database/schema hoặc tenant riêng để không đè dữ liệu của nhau.

## 25. Kiểm thử asynchronous workflow

Một workflow DSL có thể kích hoạt job hoặc event xử lý bất đồng bộ. Test không nên dùng sleep cố định rồi giả định xử lý xong.

Có thể dùng:
- Awaitility hoặc polling có timeout.
- Completion future.
- Test event listener.
- Queue inspection.
- Correlation ID.
- Barrier/latch.
- Deterministic scheduler trong test.

Ví dụ:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(
            WorkflowState.COMPLETED,
            workflowRepository.state(workflowId)
        )
    );
~~~

Timeout cần đủ ngắn để test fail nhanh nhưng đủ dài cho môi trường CI. Khi timeout, log cần có workflow ID, trạng thái hiện tại và event cuối cùng để chẩn đoán.

## 26. Kiểm thử build và deployment integration

DSL build/deployment có thể sinh task, artifact và rollout plan. Integration test nên kiểm tra:
- Task graph có dependency đúng.
- Generated source/resource được build system nhận.
- Artifact được đóng gói đúng.
- Manifest có version và checksum.
- Deployment provider nhận đúng target.
- Dry-run không tạo side effect.
- Approval gate được enforce.
- Health check sau deploy được gọi.
- Failure kích hoạt rollback/compensation theo policy.

Không nhất thiết deploy production trong test. Có thể dùng local container, mock deployment endpoint hoặc staging sandbox. Nhưng test cần dùng cùng artifact format và provider contract như production.

## 27. Testcontainers và môi trường hạ tầng tạm thời

Testcontainers là một cách phổ biến để chạy dependency như PostgreSQL, Redis, Kafka hoặc service khác trong container khi test. Lợi ích là test gần behavior thật hơn in-memory substitute.

Ví dụ khái niệm:

~~~java
@Testcontainers
class OrderRepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @Test
    void storesOrderWithDatabaseConstraints() {
        // Configure datasource using container connection details.
        // Apply migrations and exercise repository.
    }
}
~~~

Cần pin image version, tránh dùng tag thay đổi liên tục nếu muốn kết quả reproducible. Test cần chờ service ready, áp dụng migration và dọn container sau suite.

Container không phải lúc nào cũng phù hợp: startup có thể tốn thời gian, CI có thể không cho chạy Docker và test quá nhiều container làm pipeline chậm. Có thể dùng shared test service cho một số suite, nhưng cần cô lập dữ liệu và version.

## 28. Chạy integration test trong CI

Một CI pipeline có thể chia tầng:

1. Compile và static checks.
2. Unit tests.
3. Component tests.
4. Integration tests theo module.
5. Contract tests.
6. End-to-end smoke tests.
7. Security hoặc migration tests.
8. Package artifact và publish test report.

Integration test nên chạy trên môi trường được kiểm soát:
- Toolchain version pin.
- Dependency image/version pin.
- Locale/timezone cố định.
- Environment variable được khai báo.
- Secret test tách khỏi production.
- Network access giới hạn.
- Test report và log được lưu.
- Cleanup luôn chạy kể cả khi job fail.

Có thể chạy integration suite nặng theo nightly hoặc trước release, nhưng các test bao phủ ranh giới quan trọng nên có mặt trong pull request pipeline với thời gian hợp lý.

## 29. Parallel test execution

Chạy test song song giúp giảm thời gian, nhưng có thể tạo xung đột:
- Cùng port.
- Cùng database/schema.
- Cùng file output.
- Cùng plugin registry.
- Shared cache bị mutate.
- Test dùng static singleton.
- External service rate limit.

Cách giảm xung đột:
- Port động.
- Database/schema riêng.
- Temporary directory riêng.
- Test-specific namespace.
- Immutable fixture.
- Không dùng shared mutable state.
- Resource lock cho test cần độc quyền.
- Giới hạn concurrency với dependency yếu.

Nếu test chỉ pass khi chạy tuần tự, đó có thể là dấu hiệu state leakage hoặc thiếu isolation.

## 30. Test pyramid và test portfolio

Một chiến lược hợp lý có nhiều test ở các mức khác nhau:

~~~mermaid
flowchart TD
    A[Many unit tests] --> B[Component tests]
    B --> C[Focused integration tests]
    C --> D[Few end-to-end tests]
~~~

Unit test thường nhanh và rẻ nên số lượng nhiều. Integration test ít hơn nhưng bao phủ contract và các boundary quan trọng. End-to-end test ít nhất vì môi trường rộng, dễ flaky và khó chẩn đoán.

Không nên áp dụng tỷ lệ cứng cho mọi dự án. Một DSL generator có thể cần nhiều compile integration tests; một API service có thể cần nhiều database integration tests. Portfolio nên phản ánh rủi ro kiến trúc.

## 31. Tránh flaky integration test

Flaky test cho kết quả không ổn định dù code không thay đổi. Nguyên nhân thường gặp:
- Dựa vào sleep.
- Race condition.
- Thứ tự test.
- Shared state.
- Port cố định.
- Clock/timezone.
- Network không ổn định.
- Dữ liệu ngoài thay đổi.
- Retry che giấu bug.
- Cleanup không đầy đủ.

Cách xử lý:
- Dùng synchronization primitive.
- Inject clock và random seed.
- Tạo dữ liệu riêng.
- Chờ điều kiện với timeout.
- Pin dependency.
- Thu thập log khi fail.
- Không retry test failure một cách mù quáng.
- Chạy test độc lập và song song để tìm shared state.
- Phân biệt infrastructure failure với product failure.

Một test flaky không nên được đánh dấu thành công chỉ vì lần retry sau pass. Cần tìm nguyên nhân và giữ lại thông tin của lần fail đầu.

## 32. Quan sát và chẩn đoán khi test thất bại

Khi integration test fail, cần có đủ thông tin để định vị boundary:

- Test name và scenario.
- Correlation/request ID.
- DSL file và source span.
- Plugin ID/version.
- Generated artifact path.
- Database migration version.
- Event/message ID.
- Service endpoint và response status.
- Log của các component.
- Timing và retry count.
- Environment/tool versions.

Không log credential, access token hoặc dữ liệu cá nhân nhạy cảm. Có thể log hash hoặc synthetic ID để liên kết sự kiện.

Test harness nên lưu artifact khi thất bại, ví dụ generated source, compiler diagnostics, server log và database schema snapshot. Những artifact này giúp tái hiện lỗi sau khi CI job kết thúc.

## 33. Kiểm thử tương thích giữa version

DSL compiler, generator, runtime, plugin và schema có thể được phát hành độc lập. Integration test nên xác minh các tổ hợp version được hỗ trợ.

Ví dụ ma trận:

| DSL compiler | Runtime | Plugin | Kết quả mong đợi |
|---|---|---|---|
| 3.2 | 5.1 | 2.4 | Supported |
| 3.2 | 5.0 | 2.4 | Supported nếu contract cho phép |
| 3.2 | 4.0 | 2.4 | Rejected nếu runtime API quá cũ |
| 4.0 | 5.1 | 2.4 | Rejected nếu plugin chưa hỗ trợ DSL 4 |

Không cần test mọi tổ hợp có thể có. Chọn các boundary version, version mới nhất được hỗ trợ và tổ hợp không tương thích quan trọng.

Test cần xác nhận resolver từ chối sớm với diagnostic rõ ràng, thay vì để lỗi class loading hoặc runtime xuất hiện muộn.

## 34. Kiểm thử backward compatibility và migration

Khi DSL schema hoặc generated artifact thay đổi, cần kiểm tra:
- Source cũ còn parse được không.
- Migration có giữ semantics không.
- Generated API cũ có được consumer hiện tại dùng không.
- Database migration giữ dữ liệu không.
- Plugin API cũ có adapter không.
- Event consumer có đọc schema cũ không.

Một migration test nên giữ fixture từ version trước, chạy migration và so sánh semantic result. Không chỉ so sánh text vì formatter hoặc canonicalization có thể thay đổi output mà không đổi ý nghĩa.

Nếu migration không thể tự động chuyển đổi một construct, test nên xác nhận diagnostic hướng dẫn rõ thay vì âm thầm bỏ qua.

## 35. Kiểm thử hiệu năng ở ranh giới tích hợp

Integration test không chỉ xác minh functional behavior. Một số boundary cần kiểm tra hiệu năng:
- Parse và resolve workspace lớn.
- Generator với nhiều entity.
- API endpoint có query nhiều quan hệ.
- Batch event processing.
- Plugin initialization.
- Serialization payload lớn.
- Database migration trên dữ liệu nhiều bản ghi.

Performance integration test cần workload ổn định, warm-up và threshold phù hợp. Không nên dùng một ngưỡng quá chặt trên CI dùng chung vì noise phần cứng có thể tạo false failure.

Có thể theo dõi trend p50/p95, throughput, memory và cache hit thay vì chỉ một con số thời gian duy nhất.

## 36. Ví dụ Java: kiểm thử tích hợp DSL end-to-end

Một test có thể biên dịch DSL fixture, khởi động runtime và kiểm tra API:

~~~java
@Test
void dslDefinitionProducesWorkingHttpEndpoint() throws Exception {
    DslProgram program = compiler.compile(
        readFixture("orders-api.dsl")
    );

    try (ApplicationRuntime runtime =
             ApplicationRuntime.start(program, testConfiguration())) {

        HttpResponse<String> response = httpClient.send(
            HttpRequest.newBuilder(
                runtime.baseUri().resolve("/orders")
            )
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(validOrderJson()))
            .build(),
            HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(201, response.statusCode());

        JsonObject body = JsonParser.parseString(
            response.body()
        ).getAsJsonObject();

        String orderId = body.get("id").getAsString();

        assertTrue(runtime.orderRepository().exists(orderId));
    }
}
~~~

Test này đi qua compiler, generated endpoint, HTTP server, request binding, application service và persistence. Có thể bổ sung test request invalid để kiểm tra validation error và xác nhận database không thay đổi.

## 37. Quy trình xây dựng integration test

Một quy trình có thể áp dụng:

1. **Xác định boundary:** chọn các component và contract cần xác minh.
2. **Nêu scenario:** mô tả input, action và observable outcome.
3. **Chọn mức chân thực:** real dependency, container, sandbox hay test double.
4. **Tạo fixture:** DSL source, config, data và expected output nhỏ.
5. **Xây harness:** start service, database, plugin hoặc runtime.
6. **Cô lập state:** workspace, database, port và resource riêng.
7. **Thực thi qua public boundary:** gọi API/interface như consumer thật.
8. **Assert output và side effect:** response, database, event, artifact và diagnostics.
9. **Kiểm tra failure path:** timeout, conflict, invalid input và dependency outage.
10. **Cleanup:** giải phóng process, container, listener, file và data.
11. **Thu thập diagnostics:** lưu log và artifact khi fail.
12. **Tích hợp CI:** chạy đúng suite ở pull request, nightly hoặc release gate.
13. **Theo dõi flakiness và runtime:** tìm nguyên nhân test không ổn định.
14. **Giữ contract fixtures theo version:** bảo vệ compatibility lâu dài.

## 38. Nguyên tắc thiết kế

- **Kiểm tra ranh giới có rủi ro:** ưu tiên nơi dữ liệu hoặc control flow chuyển giữa component.
- **Dùng interface công khai:** test nên tương tác như consumer thật.
- **Giữ fixture nhỏ:** một scenario nên làm rõ một behavior chính.
- **Chọn dependency chân thực vừa đủ:** database hoặc broker thật khi behavior phụ thuộc implementation cụ thể.
- **Không lạm dụng mock:** mock không chứng minh protocol và wiring thực tế đúng.
- **Test generated artifact bằng compiler/runtime:** text output đúng hình thức chưa đủ.
- **Kiểm tra cả response và side effect:** đặc biệt với database, event và deployment.
- **Cô lập dữ liệu và tài nguyên:** test phải chạy độc lập và song song an toàn.
- **Inject clock và external facts:** giảm phụ thuộc thời gian và môi trường.
- **Test failure path:** lỗi dependency, transaction, retry và cleanup cũng là contract.
- **Giữ test deterministic:** tránh sleep, shared state và external data không pin.
- **Dùng contract tests giữa team:** phát hiện consumer/provider drift.
- **Test version boundary:** xác minh tổ hợp compiler, runtime, plugin và schema.
- **Thu thập diagnostics khi fail:** giúp tìm đúng boundary gây lỗi.
- **Đặt integration suite trong CI có chọn lọc:** cân bằng độ tin cậy và thời gian phản hồi.
- **Kết hợp nhiều cấp test:** unit, component, integration và end-to-end bổ sung cho nhau.

Kiểm thử tích hợp chứng minh các thành phần DSL phối hợp đúng qua những hợp đồng mà người dùng và hệ thống phụ thuộc thực sự sử dụng. Khi test đi qua boundary thực, dùng fixture có kiểm soát, cô lập database và external resource, xác minh generated artifact trong runtime, kiểm tra cả thành công lẫn thất bại và thu thập diagnostics đủ rõ, hệ thống có thể phát hiện sớm lỗi wiring, compatibility, persistence và lifecycle trước khi chúng xuất hiện trong môi trường triển khai.
