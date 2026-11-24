# Kiểm thử mẫu resource, resource bundle và danh sách interface proxy

## 1. Vì sao phải kiểm thử ba loại hints này?

Spring Boot Native Image cần biết trước những tài nguyên và cấu trúc truy cập động mà ứng dụng sẽ dùng. Reflection hints mô tả class/member; resource hints mô tả file classpath; resource bundle hints mô tả bộ thông điệp theo locale; proxy hints mô tả tổ hợp interface dùng để tạo JDK dynamic proxy.

Một registrar có thể biên dịch thành công nhưng vẫn khai báo thiếu resource hoặc sai tổ hợp interface. Lỗi thường chỉ xuất hiện khi chạy native: `ClassPathResource` trả về không tìm thấy, `ResourceBundle.getBundle()` không tìm thấy locale cần thiết, hoặc JDK proxy không tạo được vì metadata không khớp danh sách interface thực tế.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần kiểm thử riêng ba loại metadata này bằng `RuntimeHintsPredicates`, rồi xác nhận chúng được thu thập trong Spring AOT và hoạt động trên native executable. Bài viết trình bày cách xây fixture, viết unit test cho registrar, kiểm tra locale và thứ tự interface, cũng như phân biệt test metadata với native integration test.

## 2. Ba nhóm metadata và API tương ứng

Các API nằm trong package `org.springframework.aot.hint`:

| Nhu cầu | API đăng ký | Điều cần xác minh |
|---|---|---|
| Classpath file/resource | `hints.resources().registerPattern(...)` | Path/pattern thực sự được khai báo |
| Resource bundle | `hints.resources().registerResourceBundle(...)` | Base name của bundle được khai báo |
| JDK dynamic proxy | `hints.proxies().registerJdkProxy(...)` | Đúng interface combination và thứ tự |
| Kiểm thử resource | `RuntimeHintsPredicates.resource()` | Predicate match file đã đăng ký |
| Kiểm thử bundle | `RuntimeHintsPredicates.resource()` | Predicate match bundle base name |
| Kiểm thử proxy | `RuntimeHintsPredicates.proxies()` | Predicate match danh sách interface |

Các predicate API có thể có khác biệt nhỏ giữa các phiên bản Spring Framework. Dùng IDE/Javadoc theo version dependency thực tế nếu tên overload khác. Không lấy ví dụ của version mới áp dụng nguyên trạng cho project cũ mà chưa kiểm tra.

## 3. Tổ chức fixture resource trong classpath

Ví dụ cấu trúc:

```text
src/main/resources/
├── schemas/
│   ├── order-v1.json
│   └── order-v2.json
├── templates/
│   └── invoice.html
└── i18n/
    ├── messages.properties
    ├── messages_vi.properties
    └── messages_en.properties
```

Có hai nhóm tài nguyên trong ví dụ:

- File thông thường: JSON schema và HTML template.
- Resource bundle: bộ thông điệp có base name `i18n.messages` với các biến thể locale.

Đường dẫn resource classpath thường khai báo tương đối với classpath root, ví dụ `schemas/order-v1.json`. Resource bundle dùng base name theo quy tắc `ResourceBundle`, ví dụ `i18n.messages`, không dùng tên file `messages_vi.properties` làm base name.

Hãy bảo đảm fixture nằm trong `src/main/resources` nếu đây là resource production. Fixture chỉ thuộc `src/test/resources` không tự động trở thành resource của executable production.

## 4. Đăng ký resource pattern và bundle

Một registrar có thể khai báo cả hai:

```java
final class ApplicationResourceHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
                "schemas/order-*.json");

        hints.resources().registerPattern(
                "templates/*.html");

        hints.resources().registerResourceBundle(
                "i18n.messages");
    }
}
```

Gắn registrar vào cấu hình được Spring AOT xử lý:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApplicationResourceHints.class)
class ResourceConfiguration {
}
```

Pattern cần đủ cụ thể để bao phủ tài nguyên ứng dụng thực sự đọc. Nếu chỉ có hai schema version cố định, có thể đăng ký từng file cụ thể thay vì mở cả thư mục. Resource bundle đăng ký theo base name; các locale variant phù hợp sẽ được xử lý theo cơ chế bundle.

Resource hints không đóng gói file bên ngoài binary như `/etc/orders/rules.json`. File external phải được mount/cung cấp ở runtime và được đọc bằng filesystem API.

## 5. Kiểm thử registrar độc lập với Spring context

Có thể gọi registrar trực tiếp trong unit test để xác minh metadata:

```java
class ApplicationResourceHintsTest {

    @Test
    void registersSchemaAndMessageBundle() {
        RuntimeHints hints = new RuntimeHints();

        new ApplicationResourceHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("schemas/order-v1.json")
                .test(hints))
                .isTrue();

        assertThat(RuntimeHintsPredicates.resource()
                .forBundle("i18n.messages")
                .test(hints))
                .isTrue();
    }
}
```

Test dùng JUnit và AssertJ. Predicate `forResource` kiểm tra resource path được đăng ký; `forBundle` kiểm tra bundle base name. Một số phiên bản Spring có thể cung cấp overload/predicate tương ứng với cách gọi hơi khác, nên xác nhận theo dependency đang dùng.

Unit test này kiểm tra registrar đã khai báo hints trong đối tượng `RuntimeHints`. Nó chưa chứng minh Spring AOT đã phát hiện registrar hoặc Native Image đã đóng gói resource thực tế.

## 6. Kiểm thử nhiều resource path

Nếu registrar đăng ký pattern:

```java
hints.resources().registerPattern("schemas/order-*.json");
```

Có thể kiểm tra các path production dự kiến:

```java
@Test
void registersSupportedOrderSchemas() {
    RuntimeHints hints = new RuntimeHints();
    new ApplicationResourceHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.resource()
            .forResource("schemas/order-v1.json")
            .test(hints)).isTrue();

    assertThat(RuntimeHintsPredicates.resource()
            .forResource("schemas/order-v2.json")
            .test(hints)).isTrue();
}
```

Không nên chỉ kiểm tra một path đại diện nếu ứng dụng có nhiều resource được chọn theo property. Tạo danh sách test thể hiện toàn bộ phiên bản/schema/template hợp lệ.

Nếu pattern quá rộng, predicate có thể cho thấy một resource path match dù file đó không tồn tại trong artifact. Vì vậy cần thêm test xác minh resource thật có thể đọc được từ classloader:

```java
@Test
void orderSchemaExistsOnClasspath() {
    assertThat(getClass().getClassLoader()
            .getResource("schemas/order-v1.json"))
            .isNotNull();
}
```

Test classpath existence xác minh file có trong test runtime classpath; hãy chắc chắn resource thuộc main output nếu mục tiêu là đưa vào native application.

## 7. Resource bundle và base name

Java `ResourceBundle` dùng base name để tìm file theo locale. Với:

```text
i18n/messages.properties
i18n/messages_vi.properties
i18n/messages_en.properties
```

base name là:

```text
i18n.messages
```

Ví dụ đọc bundle:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.messages",
        Locale.forLanguageTag("vi"));

String greeting = bundle.getString("greeting");
```

Nội dung `messages_vi.properties`:

```properties
greeting=Xin chào
order.created=Tạo đơn hàng thành công
```

Nội dung `messages_en.properties`:

```properties
greeting=Hello
order.created=Order created successfully
```

Khi kiểm thử, dùng locale tường minh thay vì dựa vào default locale của máy chạy test. Điều này tránh test pass trên máy developer nhưng fail trong CI/container do locale mặc định khác.

## 8. Kiểm thử resource bundle hint

Có thể kiểm tra bundle base name đã đăng ký:

```java
@Test
void registersMessageBundle() {
    RuntimeHints hints = new RuntimeHints();
    new ApplicationResourceHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.resource()
            .forBundle("i18n.messages")
            .test(hints))
            .isTrue();
}
```

Predicate này xác minh metadata đăng ký bundle. Để xác minh nội dung và locale, thêm test thực tế:

```java
@Test
void loadsVietnameseAndEnglishMessages() {
    ResourceBundle vi = ResourceBundle.getBundle(
            "i18n.messages",
            Locale.forLanguageTag("vi"));

    ResourceBundle en = ResourceBundle.getBundle(
            "i18n.messages",
            Locale.forLanguageTag("en"));

    assertThat(vi.getString("greeting")).isEqualTo("Xin chào");
    assertThat(en.getString("greeting")).isEqualTo("Hello");
}
```

Test này kiểm tra bundle được tìm thấy trên JVM test classpath và key có nội dung đúng. Native integration test vẫn cần thiết để xác nhận bundle đã được đưa vào executable.

Cũng nên kiểm tra fallback locale theo yêu cầu sản phẩm. Java ResourceBundle có quy tắc fallback theo locale và default bundle; nếu ứng dụng cần behavior cụ thể, viết test cho locale không có file riêng và bundle mặc định.

## 9. Không nhầm bundle base name với resource filename

Một lỗi phổ biến là đăng ký:

```java
hints.resources().registerResourceBundle(
        "i18n/messages_vi.properties");
```

Đây không phải base name chuẩn của ResourceBundle. Cần đăng ký:

```java
hints.resources().registerResourceBundle(
        "i18n.messages");
```

Base name dùng dấu chấm phân cách package/path theo quy ước ResourceBundle. Tên locale suffix như `_vi` hoặc `_en` được runtime dùng để tìm variant; không thêm suffix vào base name khi muốn hỗ trợ nhiều locale của cùng bundle.

Nếu ứng dụng sử dụng Spring MessageSource thay vì gọi ResourceBundle trực tiếp, hãy kiểm tra cấu hình basename của MessageSource và test trên native theo đúng API thực tế. Không giả định basename của Spring luôn giống cấu hình resource tùy biến nếu có nhiều bundle.

## 10. Kiểm thử danh sách interface proxy

JDK dynamic proxy được xác định bởi danh sách interface có thứ tự. Ví dụ:

```java
hints.proxies().registerJdkProxy(
        OrderOperations.class,
        Auditable.class);
```

Unit test:

```java
@Test
void registersOrderProxyInExpectedOrder() {
    RuntimeHints hints = new RuntimeHints();
    new OrderProxyHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.proxies()
            .forInterfaces(
                    OrderOperations.class,
                    Auditable.class)
            .test(hints))
            .isTrue();
}
```

Dùng đúng thứ tự trong cả registrar và predicate. Không thay `containsExactly` bằng `containsExactlyInAnyOrder` khi kiểm tra proxy runtime; thứ tự là một phần của proxy definition.

Một hint cho `[OrderOperations, Auditable]` không nên được coi là bao phủ `[Auditable, OrderOperations]`. Nếu ứng dụng thật sự tạo cả hai biến thể, đăng ký và kiểm thử từng tổ hợp.

## 11. So sánh metadata với proxy runtime thực tế

Ngoài kiểm tra predicate, tạo proxy trên JVM và xác nhận interface list:

```java
Object proxy = Proxy.newProxyInstance(
        OrderOperations.class.getClassLoader(),
        new Class<?>[] {
                OrderOperations.class,
                Auditable.class
        },
        (instance, method, args) -> null);

assertThat(proxy.getClass().getInterfaces())
        .containsExactly(
                OrderOperations.class,
                Auditable.class);
```

Đối với proxy do Spring AOP tạo, lấy bean từ ApplicationContext và kiểm tra object thực tế. Advisor, introduction hoặc framework wrapper có thể bổ sung interface; đừng suy luận danh sách cuối cùng chỉ từ interface trên implementation class.

Khi viết registrar, đối chiếu interface list thực tế từ test với danh sách được đăng ký. Nếu danh sách được tạo động, cần xác định tất cả tổ hợp hợp lệ ở build time hoặc chuẩn hóa factory để dùng một thứ tự duy nhất.

## 12. Tổ chức test cho registrar tổng hợp

Một ứng dụng có thể có nhiều registrar riêng cho resource, bundle và proxy. Có thể test riêng từng registrar để lỗi dễ định vị, rồi có một test tổng hợp xác nhận tất cả metadata quan trọng.

Ví dụ cấu trúc test:

```text
src/test/java/
└── com/example/nativeconfig/
    ├── ResourceHintsTest.java
    ├── MessageBundleHintsTest.java
    ├── ProxyHintsTest.java
    └── ApplicationHintsTest.java
```

Không nên gom mọi assertion vào một test dài không có ngữ cảnh. Khi test resource fail, cần biết resource path nào; khi proxy fail, cần biết tổ hợp interface nào sai.

Test tổng hợp hữu ích để bảo đảm cấu hình AOT của ứng dụng vẫn bao gồm tất cả nhóm hints sau refactor. Nhưng nó không thay thế test chi tiết của từng registrar.

## 13. Phân biệt ba lớp kiểm thử

| Lớp test | Điều được xác minh | Điều chưa được chứng minh |
|---|---|---|
| Registrar unit test | RuntimeHints có entry mong muốn | Registrar đã được AOT thu thập |
| Classpath/bundle/proxy JVM test | Resource và proxy hoạt động trên JVM | Metadata đã nằm trong native executable |
| Native integration test | Binary native đọc resource/bundle và tạo proxy thực tế | Mọi nhánh runtime khác đều đã được bao phủ |

Một test predicate pass không bảo đảm native build thành công. Một native build pass cũng không bảo đảm resource bundle locale hiếm hoặc proxy combination ít dùng hoạt động. Cần test trên đúng executable và chạy các scenario có ý nghĩa.

## 14. Native integration test cho resource và bundle

Tạo một service đơn giản dùng resource:

```java
@Component
class OrderSchemaLoader {

    String load(String version) throws IOException {
        String path = "schemas/order-" + version + ".json";

        try (InputStream input =
                getClass().getClassLoader()
                        .getResourceAsStream(path)) {
            if (input == null) {
                throw new FileNotFoundException(path);
            }
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
```

Native test nên gọi service với mọi version hợp lệ và xác nhận nội dung parse được. Đối với bundle, chạy locale vi/en và kiểm tra key. Đối với proxy, tạo proxy qua cùng factory production, xác nhận interface và gọi method.

Có thể dùng native test task nếu plugin hỗ trợ, hoặc khởi chạy executable native rồi gửi HTTP request. Cách black-box giúp xác minh cả packaging, resource, ApplicationContext và runtime behavior.

## 15. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Resource predicate fail | Sai path hoặc registrar không đăng ký pattern | Đối chiếu classpath path và registrar |
| Predicate pass nhưng native resource null | Registrar không được AOT thu thập hoặc resource không nằm trong main artifact | Kiểm tra AOT output và JAR/resource inputs |
| Bundle không tìm thấy trên native | Sai base name hoặc thiếu bundle hint | Đăng ký base name đúng và test locale |
| Chỉ locale vi fail | Thiếu variant, sai tên file hoặc fallback không như mong muốn | Kiểm tra messages_vi và test locale tường minh |
| Proxy predicate fail | Sai interface list hoặc thứ tự | Đối chiếu danh sách runtime và registrar |
| Predicate pass nhưng native proxy fail | AOT chưa thu thập hint hoặc proxy runtime có interface khác | Kiểm tra generated metadata và proxy class thực tế |
| JVM pass, native fail | Metadata chưa được đóng gói hoặc path khác | Chạy native integration và xem build diagnostics |
| Test CI khác máy dev | Default locale hoặc case-sensitive path | Đặt locale rõ ràng, chuẩn hóa tên resource |

Khi điều tra, xác định test nào đang fail: predicate, JVM resource/proxy behavior, AOT collection hay native runtime. Không thêm metadata rộng trước khi biết lớp nào thiếu.

## 16. Bài thực hành: kiểm thử resource, bundle và proxy

**Bối cảnh:** dịch vụ Order API đọc hai JSON schema, hiển thị thông báo tiếng Việt/Anh và tạo JDK proxy triển khai `OrderOperations` cùng `Auditable`.

**Bước 1 — Tạo fixtures.** Đặt `schemas/order-v1.json`, `schemas/order-v2.json`, `i18n/messages.properties`, `messages_vi.properties` và `messages_en.properties` trong main resources.

**Bước 2 — Viết registrar.** Đăng ký schema pattern, bundle base name `i18n.messages` và proxy interface list theo đúng thứ tự.

**Bước 3 — Viết predicate tests.** Dùng `RuntimeHintsPredicates.resource()` kiểm tra từng schema/bundle; dùng `RuntimeHintsPredicates.proxies()` kiểm tra đúng interface combination.

**Bước 4 — Viết behavior tests trên JVM.** Đọc schema, lấy message theo locale vi/en, tạo proxy và assert interface list bằng `containsExactly`.

**Bước 5 — Xác nhận AOT collection.** Gắn registrar vào configuration thuộc ApplicationContext và chạy Spring AOT.

**Bước 6 — Build native.** Dùng Native Build Tools phù hợp, kiểm tra metadata được thu thập và executable tạo thành công.

**Bước 7 — Chạy native integration.** Gọi các luồng đọc schema, hiển thị message theo locale và tạo proxy; dùng cùng fixture với JVM tests.

**Bước 8 — Kiểm tra biến thể lỗi.** Thử resource version không tồn tại, locale không có variant riêng và proxy interface order khác để xác minh fallback/error behavior.

Tiêu chí hoàn thành: registrar unit tests pass; classpath resource và bundle có nội dung đúng; proxy runtime có đúng interface list và thứ tự; cùng behavior được xác nhận trên native executable.

## 17. Kết luận

Kiểm thử resource, resource bundle và proxy cần xác minh cả **metadata được đăng ký** lẫn **hành vi thực tế**. `RuntimeHintsPredicates.resource()` giúp kiểm tra resource path và bundle base name; `RuntimeHintsPredicates.proxies()` kiểm tra tổ hợp interface. Với JDK proxy, thứ tự interface phải khớp proxy runtime. Với resource bundle, dùng base name đúng và kiểm tra locale tường minh.

Registrar unit tests giúp phát hiện lỗi khai báo sớm, nhưng chỉ native integration test mới xác nhận metadata đã được Spring AOT thu thập và executable sử dụng được resource/proxy. Hãy dùng cùng fixtures, kiểm tra từng locale/interface combination quan trọng và chạy trong runtime container đích trước khi phát hành.
