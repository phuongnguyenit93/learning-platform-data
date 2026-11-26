# Đọc release notes của dòng đích trước khi đổi dependency

Nâng cấp một ứng dụng **Spring Web Flow** đang hoạt động ổn định không đơn thuần là đổi số phiên bản của `spring-webflow` rồi chạy lại build. Ứng dụng có thể phụ thuộc vào hành vi của **flow registry**, **FlowExecutor**, **state/event/transition**, form binding, validation, các scope, URL tiếp tục flow và cách tích hợp với Spring MVC, Spring Security hoặc JSF. Một thay đổi nhỏ về hạ tầng cũng có thể khiến luồng nhiều bước bị mất trạng thái, không resolve được view, hoặc chỉ lỗi sau khi người dùng bấm Back hay hết phiên.

Trong chương **Nâng cấp ứng dụng cũ**, bài học này tập trung vào một quy tắc: **xác định và đọc release notes của dòng phiên bản đích trước khi thay đổi dependency**. Ta sẽ xây dựng quy trình đọc có mục tiêu, ghi lại yêu cầu tương thích và biến mỗi rủi ro thành một phép kiểm chứng. Không giả định trước phiên bản hiện tại hay đích cụ thể của dự án.

## 1. Vì sao phải đọc release notes trước khi sửa build?

Một dependency có thể có API trông quen thuộc ở thời điểm biên dịch nhưng hành vi chạy đã thay đổi. Ví dụ, application context vẫn khởi động được, nhưng một flow dùng `viewScope` có thể biểu hiện khác khi quay lại trang trước; hoặc cơ chế xử lý URL thay đổi khiến request gửi event không tiếp tục đúng execution.

Chỉ nhìn thông báo “build thành công” không giúp phát hiện các trường hợp này. **Release notes**, **upgrade/migration guide** và các ghi chú tương thích cho biết những điểm dự án cần rà soát trước, nhờ vậy tránh cập nhật hàng loạt dependency rồi mới lần ngược nguyên nhân lỗi.

| Nguồn thông tin | Thường trả lời câu hỏi gì? | Cách sử dụng |
| --- | --- | --- |
| **Release notes / changelog của Spring Web Flow** | Bản đích thêm, sửa, thay đổi hoặc loại bỏ hành vi nào? | Xác định breaking change, bug fix, known issue và tính năng liên quan flow |
| **Upgrade hoặc migration guide** | Phải thay đổi cấu hình/API/mẫu tích hợp như thế nào? | Lập danh sách công việc sửa mã nguồn, XML và cấu hình |
| **Compatibility / system requirements** | Cần dòng Spring Framework, Java, Servlet, JSF, Security nào? | Đặt điều kiện đầu vào trước khi thay dependency |
| **Reference documentation và API docs đúng phiên bản** | Cấu hình mới được hỗ trợ, khuyến nghị ra sao? | Kiểm tra lại chữ ký API, namespace XML, hành vi repository/scope |
| **Issue tracker và release tag/source** | Thay đổi hoặc lỗi cụ thể được xử lý ở commit/issue nào? | Tìm chi tiết khi release notes chỉ mô tả ngắn |

**Không phải nguồn nào cũng có cùng nội dung.** Một bản phát hành có thể chỉ có danh sách thay đổi ngắn trên GitHub; dự án có thể phải đọc thêm hướng dẫn Spring Framework/Spring Boot và tài liệu API ứng với phiên bản đó. Không diễn giải việc “không thấy nhắc tới” thành “chắc chắn không có thay đổi”.

## 2. Xác định rõ dòng hiện tại và dòng đích

Trước khi tìm release notes, lập một bản chụp kỹ thuật của ứng dụng. Tối thiểu cần phân biệt:

- **Phiên bản đang chạy thực tế** của `org.springframework.webflow:spring-webflow` và các module Spring Web Flow liên quan, nếu có.
- **Phiên bản đề xuất** và **dòng đích**: đang ở nhánh maintenance nào, nâng patch/minor hay chuyển major.
- Phiên bản **Spring Framework** và **Spring Boot** nếu dự án dùng Boot.
- **JDK** khi build và khi chạy, servlet container và phiên bản API Servlet.
- Những tích hợp thực tế: Spring MVC, Spring Security, JSF, Hibernate/JPA, cơ chế quản lý session và deployment nhiều node.

Mẫu ghi nhận ban đầu:

| Thành phần | Hiện tại | Đích dự kiến | Cần xác nhận |
| --- | --- | --- | --- |
| Spring Web Flow | `CURRENT_WEBFLOW` | `TARGET_WEBFLOW` | Dòng đích còn hỗ trợ cấu hình/luồng đang dùng? |
| Spring Framework | `CURRENT_SPRING` | `TARGET_SPRING` | Tương thích với Web Flow đích? |
| Spring Boot, nếu có | `CURRENT_BOOT` | `TARGET_BOOT` | Dependency management và auto configuration? |
| Java | `CURRENT_JAVA` | `TARGET_JAVA` | Build tool, runtime và baseline JDK? |
| Servlet container | `CURRENT_CONTAINER` | `TARGET_CONTAINER` | API `javax.servlet.*` hay `jakarta.servlet.*`? |
| Tích hợp JSF/Security | `CURRENT_INTEGRATIONS` | `TARGET_INTEGRATIONS` | Module tương thích, namespace và cơ chế bảo mật? |

Các chuỗi `CURRENT_*` / `TARGET_*` ở đây là **ô trống cần điền sau khi kiểm tra dự án**, không phải tên phiên bản thật.

Nếu dự án dùng Maven, lệnh sau giúp quan sát dependency đã được giải quyết:

```bash
mvn dependency:tree -Dincludes=org.springframework.webflow
mvn dependency:tree -Dincludes=org.springframework
```

Với Gradle, có thể sử dụng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflow --configuration runtimeClasspath
```

Nếu dùng Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. Các lệnh là ví dụ để chạy trong dự án phù hợp; cần kiểm tra tên module/cấu hình Gradle thực tế trước. Điều quan trọng là **phiên bản resolved ở runtime**, vì version trong `pom.xml` hoặc `build.gradle` có thể bị BOM, dependency management hoặc quy tắc resolution thay đổi.

## 3. Tìm đúng tài liệu chính thức của phiên bản đích

Đối với Spring Web Flow, có thể bắt đầu từ:

- [Danh sách Releases của spring-projects/spring-webflow](https://github.com/spring-projects/spring-webflow/releases)
- [Các tag của spring-projects/spring-webflow](https://github.com/spring-projects/spring-webflow/tags)
- [Trang dự án Spring Web Flow](https://spring.io/projects/spring-webflow)
- [Tài liệu Spring Framework](https://docs.spring.io/spring-framework/reference/) và các hướng dẫn nâng cấp của dòng Spring Framework tương ứng

**Mục tiêu là tài liệu gắn với phiên bản sẽ triển khai**, không chỉ nội dung hiển thị của nhánh mới nhất. Nếu nâng cùng lúc Spring Boot, Spring Security hoặc JSF, phải đọc release notes và migration guide của **chính những thành phần đó**.

Quy trình tìm đúng tài liệu:

1. Xác nhận mã phiên bản đích đã được phát hành và artifact có thể resolve từ repository sử dụng trong dự án.
2. Mở release/tag tương ứng. Kiểm tra ngày phát hành, điều kiện hỗ trợ và link reference/migration guide nếu có.
3. Nếu nâng qua nhiều bản, đọc **các thay đổi nằm giữa bản hiện tại và bản đích**, đặc biệt tại ranh giới major/minor; không chỉ đọc riêng changelog của bản cuối.
4. Đối chiếu release notes với dependency management của bản Spring Boot hoặc framework dự kiến để tránh chọn tổ hợp thư viện mâu thuẫn.
5. Ghi lại URL đến tài liệu đã đọc, phiên bản, nội dung liên quan và quyết định cho từng vấn đề.

Ví dụ về phạm vi đọc: nếu nâng giả định từ `A.1` lên `B.3`, cần xem những thay đổi trong các release `A.2`, `B.0`, `B.1`, `B.2`, `B.3` nếu chúng nằm trên tuyến nâng cấp, rồi xem migration guide từ A sang B. Đây là ký hiệu minh họa, không đại diện cho version thật của Spring Web Flow.

**Cẩn thận với “latest”:** release mới nhất tại thời điểm đọc chưa chắc phù hợp với baseline JDK, Spring Framework hoặc lịch hỗ trợ của ứng dụng đang dùng. “Bản đích tốt” là bản đáp ứng yêu cầu tương thích, bảo trì, bảo mật và khả năng kiểm thử đã được xác minh.

## 4. Đọc release notes theo thứ tự rủi ro

Thứ tự đọc có thể bắt đầu bằng những thay đổi dễ chặn nâng cấp nhất:

| Ưu tiên | Mục cần rà trong release notes | Hệ quả có thể gặp ở Spring Web Flow |
| --- | --- | --- |
| 1 | **Required versions / baseline**: Java, Spring, Servlet, JSF | Ứng dụng không biên dịch hoặc context không thể khởi tạo |
| 2 | **Removed / incompatible APIs** | Bean cấu hình, extension point, listener, validator hoặc adapter không còn tương thích |
| 3 | **Namespace / schema / configuration changes** | Flow XML, flow registry hoặc FlowExecutor không dựng được |
| 4 | **Behavior changes** | Event, transition, binding, exception handling, redirect và execution lifecycle khác trước |
| 5 | **Security, session, serialization, persistence** | Lỗi resume flow, dữ liệu scope, session clustering, CSRF hoặc quyền truy cập |
| 6 | **Bug fixes / regressions / known issues** | Hành vi cũ thay đổi vì lỗi được sửa; cần xem ứng dụng có đang dựa vào hành vi cũ không |
| 7 | **Deprecations / future removals** | Có thể vẫn chạy nhưng phải lên kế hoạch thay API trước đợt nâng tiếp theo |

Các cụm từ nên tìm trực tiếp trong release notes gồm: `breaking`, `incompatible`, `requires`, `deprecated`, `removed`, `migration`, `security`, `session`, `serialization`, `Web Flow`, `binding`, `MVC` và `JSF`. Đây là cách lọc để **định vị**, sau đó phải đọc cả ngữ cảnh và phạm vi áp dụng.

### Đừng bỏ qua thay đổi trong dependency bắc cầu

Một dòng Spring Web Flow có thể được sử dụng cùng với các module thuộc Spring Framework, Spring Security hoặc thư viện giao diện. Nếu nâng Web Flow làm thay đổi phiên bản transitive mà dự án không ghi trực tiếp, lỗi có thể xuất hiện ở code khác ngoài package `org.springframework.webflow`.

Cần phân biệt:

- **Direct dependency**: do ứng dụng khai báo rõ.
- **Transitive dependency**: do thư viện khác kéo vào.
- **Managed version**: do BOM hoặc dependency management chọn.
- **Resolved version**: phiên bản cuối cùng nằm trên classpath khi build/chạy.

Một changelog nói “compatible with Spring X” chưa chứng minh ứng dụng đang chạy đúng X. Dependency tree và kết quả runtime là bằng chứng bổ sung cần đối chiếu.

## 5. Một tình huống cần đọc tài liệu của nhiều dòng cùng lúc

Giả sử ứng dụng cũ dùng Spring Web Flow trong môi trường Spring MVC và được đề xuất chuyển sang một nền tảng Spring Framework mới có yêu cầu Jakarta. Trước khi đổi phiên bản Web Flow, cần đặt những câu hỏi sau:

- **Spring Web Flow đích** có hỗ trợ dòng Spring Framework đó không?
- **Servlet API** ở môi trường đích dùng tên package nào? Có mã tự viết còn import `javax.servlet.*` trong khi nền tảng đích yêu cầu `jakarta.servlet.*` không?
- **Spring Security** và các integration bean đang dùng có tương thích không? Cách cấu hình authentication, authorization và CSRF có cần thay đổi không?
- Nếu ứng dụng có **JSF**, các thành phần JSF và adapter tích hợp có hỗ trợ nền tảng đích không?
- **Servlet container** và JDK có đúng baseline mà release notes yêu cầu không?

Đây là tình huống **giả định để minh họa cách kiểm tra điều kiện**, không khẳng định bất kỳ phiên bản Spring Web Flow cụ thể nào tương thích với một dòng Jakarta cụ thể. Phải dựa vào release notes thật của **tất cả các thành phần liên quan** để kết luận.

Ví dụ, khi một dòng framework đổi từ namespace `javax.*` sang `jakarta.*`, việc chỉ đổi số phiên bản dependency có thể gây `ClassNotFoundException` hoặc `NoClassDefFoundError` nếu classpath còn trộn thư viện thuộc hai hệ namespace. Cần xác định rõ thành phần áp dụng; không tìm thay thế toàn bộ chuỗi `javax` trong dự án một cách máy móc, vì một số package không thuộc phạm vi chuyển đổi.

## 6. Đối chiếu nội dung release notes với nơi dùng Web Flow

Sau khi khoanh vùng thay đổi, hãy rà soát **các điểm tích hợp mà ứng dụng thật sự dùng**. Không phải mọi mục trong release notes đều ảnh hưởng dự án.

| Cơ chế trong ứng dụng | Dấu hiệu nên tìm khi đọc tài liệu đích | Bài kiểm thử cần chuẩn bị |
| --- | --- | --- |
| `flow-registry`, `flow-location` | Thay đổi tạo registry, XML parser/schema, resource path | Khởi động context; liệt kê được flow ID; mở flow |
| `FlowExecutor` / `FlowHandlerMapping` / `FlowHandlerAdapter` | Thay đổi integration với Spring MVC và định tuyến | Gọi URL bắt đầu flow; gửi event; kiểm tra status/redirect |
| `view-state`, `action-state`, `decision-state` | Khác biệt state transition, action, guard | Đi hết happy path và các nhánh từ chối/quay lại |
| `subflow-state` | Thay đổi tham số in/out và conversation | Gọi subflow, nhận kết quả, về đúng state cha |
| `flowScope`, `viewScope`, `conversationScope` | Thay đổi vòng đời state/scope | Form nhiều bước giữ đúng dữ liệu và dọn scope khi kết thúc |
| Binding / validation | Thay đổi converter, validator, error handling | Nhập dữ liệu sai, giữ form và thông báo lỗi đúng |
| Execution key/repository | Thay đổi snapshot, serialization, max execution, URL | Refresh, Back, nhiều tab, timeout và resume |
| Spring Security integration | Thay đổi bảo vệ flow, URL, CSRF | Chỉ user được phép vào state nhạy cảm; request POST hợp lệ |
| JSF (nếu dùng) | Thay đổi adapter, scope hoặc thư viện JSF hỗ trợ | Điều hướng view JSF, action và trạng thái component |
| Exception recovery | Thay đổi exception mapping/listener | Kịch bản lỗi nghiệp vụ có hướng khôi phục an toàn |

Có thể ghi kết quả rà soát bằng bảng **“thay đổi → nơi bị ảnh hưởng → bằng chứng kiểm thử”**. Điều này giúp người duyệt nâng cấp biết chính xác vì sao cần một sửa đổi và làm thế nào để xác minh nó.

## 7. Biến một dòng release notes thành công việc cụ thể

Giả sử release notes của một phiên bản đích **có đề cập** việc thay đổi cách quản lý snapshot hoặc khôi phục flow execution. Nội dung này chỉ là tình huống mẫu, **không phải trích dẫn một bản phát hành cụ thể**.

Thay vì ghi chú “có thay đổi về session”, cần lập phiếu đánh giá:

| Thuộc tính | Ví dụ ghi nhận |
| --- | --- |
| Nguồn | URL release note, tag `TARGET_WEBFLOW`, tiêu đề hoặc issue liên quan |
| Thay đổi | “Cơ chế snapshot/repository có thay đổi” (giả định) |
| Mức ảnh hưởng | Trung bình/Cao nếu dự án dùng Back/Forward và form dài |
| Điểm tích hợp | `FlowExecutionRepository`, policy session, URL có `execution` |
| Kịch bản lỗi | Người dùng trở lại view trước rồi submit; key cũ không resume được |
| Hành động | Đối chiếu cấu hình repository; điều chỉnh logic điều hướng nếu tài liệu đích yêu cầu |
| Tiêu chí nghiệm thu | Form tiếp tục đúng execution; back/resume hoạt động đúng chính sách; không ghi đơn hàng hai lần |

Một mục release notes nói về **bug fix binding** nên dẫn tới test dữ liệu nhập sai/hợp lệ. Một mục nói về **resource loading** nên dẫn tới test khởi tạo `flowRegistry`. Một mục nói về **security** nên có test quyền và CSRF. Mỗi dòng có bằng chứng riêng; test happy path duy nhất thường không đủ.

### Ma trận tác động để quyết định có thể nâng chưa

| Kết quả đọc tài liệu | Quyết định trước khi đổi dependency |
| --- | --- |
| Bản đích yêu cầu JDK/framework/container khác hẳn môi trường hiện có | Chặn nâng cấp cho đến khi lập kế hoạch đổi nền tảng |
| API hoặc integration đang dùng đã bị loại bỏ | Phải sửa mã/cấu hình và chuẩn bị test trước |
| Có behavior change đối với execution, binding hoặc redirect | Thiết kế regression test tương ứng và phương án khôi phục |
| Chỉ có bug fix không ảnh hưởng trực tiếp phần đang dùng | Vẫn chạy smoke/regression test căn bản và đối chiếu dependency tree |
| Release notes không đủ thông tin tương thích | Tra reference, migration guide, artifact metadata hoặc issue chính thức; ghi trạng thái “chưa xác minh” |

Quyết định **“chưa xác minh”** là hợp lệ. Không nên đổi dependency chỉ vì mã build hiện tại chấp nhận version mới.

## 8. Ví dụ quy trình nâng cấp trên Maven và Gradle

Sau khi đã đối chiếu compatibility và chọn version đích, thay đổi trong build nên nhỏ, rõ ràng và có thể quay lại.

**Maven — mô hình dùng thuộc tính version:**

```xml
<properties>
    <!-- Giá trị sẽ được thay bằng phiên bản đích đã xác minh -->
    <spring-webflow.version>TARGET_VERSION_VERIFIED</spring-webflow.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.webflow</groupId>
        <artifactId>spring-webflow</artifactId>
        <version>${spring-webflow.version}</version>
    </dependency>
</dependencies>
```

**Gradle (Groovy DSL) — ví dụ quản lý version ở một nơi:**

```groovy
def springWebFlowVersion = providers.gradleProperty("springWebFlowVersion").get()

dependencies {
    implementation "org.springframework.webflow:spring-webflow:$springWebFlowVersion"
}
```

```properties
# gradle.properties: điền bản đã xác minh từ release notes
springWebFlowVersion=TARGET_VERSION_VERIFIED
```

`TARGET_VERSION_VERIFIED` là placeholder, **không phải version có thể sử dụng ngay**. Nếu dự án đã có BOM hoặc version catalog, hãy điều chỉnh ví dụ theo cách quản lý version của dự án và xác định rõ thư viện nào được BOM quản lý. Không tự cưỡng ép một dependency sang bản khác với tổ hợp framework mà tài liệu đích chưa xác nhận tương thích.

Trình tự thực hiện hợp lý:

1. Lưu lại baseline hiện tại: dependency tree, JDK, kết quả khởi động và smoke test chính.
2. Chọn bản đích sau khi đọc release notes và ghi mọi yêu cầu tương thích.
3. Thay đổi tập dependency **nhỏ nhất** đáp ứng tổ hợp được hỗ trợ.
4. Giải quyết dependency tree mới, xác nhận không có bản Spring trùng hoặc namespace `javax`/`jakarta` mâu thuẫn.
5. Chạy compile/test, khởi động context và test các flow theo ma trận rủi ro.
6. Ghi lại khác biệt trước/sau và phương án rollback bằng version/build artifact cũ nếu có lỗi chưa khắc phục.

Mục đích của ví dụ là thể hiện điểm đặt version. Nó không thể thay thế kiểm tra cấu hình build thực của dự án.

## 9. Danh sách kiểm thử dựa trên release notes

Đối với một ứng dụng Spring Web Flow phục vụ quy trình nhiều bước, bộ regression test tối thiểu nên bao phủ:

**Khởi động và đăng ký flow:**

- Application context tạo được bean registry/executor/handler cần thiết.
- Flow definition XML có thể parse, các state/transition được resolve.
- Những flow ID dùng trong URL hoặc subflow vẫn tồn tại.
- Không xuất hiện `BeanCreationException`, `NoSuchFlowDefinitionException` hoặc lỗi namespace vì thay thư viện.

**Điều hướng và giao diện:**

- Bắt đầu flow từ URL, chuyển `view-state → action-state → view-state/end-state` theo thiết kế.
- Form submit gửi đúng `_eventId` và execution key.
- Giao diện render đúng JSP/Thymeleaf/JSF (tùy ứng dụng).
- Nhánh Back/Cancel/Error đi đến state phù hợp.

**Dữ liệu và thời gian sống:**

- Dữ liệu `flowScope` và `viewScope` còn đúng khi chuyển bước; validation không xóa dữ liệu người dùng ngoài dự kiến.
- Session timeout có thông báo và đường khởi động lại hợp lý.
- Refresh, Back/Forward, mở hai tab, gửi lại request theo đúng chính sách repository.
- Nếu chạy nhiều node, thử thực tế với cách đồng bộ session hoặc phân phối request đang triển khai.

**Bảo mật và nghiệp vụ:**

- Chặn truy cập trái phép vào thao tác nhạy cảm.
- CSRF token được kiểm tra ở các request thay đổi trạng thái.
- Thanh toán/đặt hàng không bị tạo hai lần do retry, refresh hoặc back.
- Exception recovery thể hiện đúng kết quả nghiệp vụ, không làm rò rỉ dữ liệu.

Không phải mọi test đều cần viết mới; hãy chọn test dựa trên sự khác biệt mà release notes chỉ ra, kết hợp smoke test các flow quan trọng nhất. **Test phải xác thực hành vi**, không chỉ kiểm tra bean có tồn tại.

## 10. Đọc log sau khi đổi dependency để đối chiếu giả thuyết

Khi phát sinh lỗi sau nâng cấp, đừng quy ngay lỗi đó cho `spring-webflow`. Tìm thời điểm lỗi và `Caused by` sâu nhất:

| Triệu chứng | Điều cần đối chiếu với release notes |
| --- | --- |
| `NoClassDefFoundError` / `ClassNotFoundException` | JDK, Servlet/Jakarta API hoặc dependency còn thiếu/trộn |
| `NoSuchMethodError` | Phiên bản classpath có mâu thuẫn binary API không? |
| `BeanCreationException` khi khởi tạo `flowRegistry` | Parser/XML namespace, config bean, resource và framework baseline |
| `NoSuchFlowDefinitionException` | Flow ID, registry và MVC mapping có thay đổi? |
| `NoSuchFlowExecutionException` hoặc resume lỗi | Repository, session, snapshot và vòng đời execution |
| Binding/validation lỗi nhưng flow vẫn chạy | Converter, validator, model/binder và phần đổi hành vi trong tài liệu đích |
| Login hoặc CSRF chặn request tiếp tục | Spring Security integration, cấu hình security filter và các thay đổi liên quan |

Một lỗi `NoSuchMethodError` có thể đến từ việc một module Spring được resolve sang version không tương thích dù khai báo trực tiếp của Web Flow đã đúng. Vì vậy, đối chiếu **dependency tree sau nâng cấp** với ma trận yêu cầu là bước không thể bỏ.

Nếu lỗi chỉ xuất hiện khi nhấn Back hoặc sau session timeout, tái hiện đúng chuỗi thao tác; test khởi động đơn thuần sẽ không phản ánh được vấn đề của repository/snapshot.

## 11. Hồ sơ quyết định nâng cấp có thể review

Trước khi tạo PR hoặc triển khai, nên có một bản ghi ngắn:

```text
Ứng dụng: checkout legacy
Thành phần: Spring Web Flow
Phiên bản hiện tại: [ghi version resolved]
Dòng/phiên bản đích: [ghi target đã xác minh]
Nguồn release notes: [URL + tag + ngày tra cứu]
Upgrade guide: [URL và phiên bản, nếu có]
Compatibility:
  - Java: [mức yêu cầu và runtime thực tế]
  - Spring Framework/Boot: [tổ hợp đã xác nhận]
  - Servlet/container: [mức yêu cầu]
  - Security/JSF: [nếu dùng]
Thay đổi ảnh hưởng:
  - [mục release notes] -> [nơi dùng] -> [test]
Rủi ro chưa giải quyết: [ghi rõ hoặc "không có sau kiểm tra"]
Kết quả baseline: [build/context/smoke/regression]
Kết quả trên bản đích: [pass/fail và log/CI link]
Rollback: [commit, version và artifact dùng để quay lại]
Quyết định: [cho phép / cần bổ sung / chặn]
```

Các trường trong ngoặc vuông là chỗ cần điền, không phải dữ liệu của một phiên bản thật. Hồ sơ này giúp người tiếp nhận hiểu **vì sao đã chọn version** và **đã kiểm tra những điểm nào** mà không phải dò toàn bộ cuộc trao đổi.

### Dấu hiệu nên dừng lại trước khi thay dependency

- Tài liệu chính thức chưa xác minh tương thích Spring Web Flow đích với Spring Framework/runtime đã chọn.
- Có breaking change ảnh hưởng API hoặc integration đang được dùng nhưng chưa có hướng sửa.
- Dependency tree hiện tại đã lẫn nhiều dòng Spring, chưa xác định được version runtime.
- Thiếu phương án kiểm thử cho các flow quan trọng, nhất là flow liên quan dữ liệu/tiền.
- Không có hướng rollback hoặc dữ liệu lưu trong session/serialized state có thể không tương thích sau triển khai.

Dừng để thu thập bằng chứng ở các điểm này rẻ hơn việc khắc phục lỗi production khi người dùng đang ở giữa quy trình thanh toán.

## 12. Bài thực hành: đánh giá một đề xuất nâng cấp

Giả sử nhóm đề nghị thay version của `spring-webflow` từ `CURRENT_WEBFLOW` sang `TARGET_WEBFLOW`. Chưa ai đưa ra release notes. Hệ thống đang dùng Spring MVC, form binding, `flowScope`, URL có `execution` và một cụm ứng dụng hai node.

**Nhiệm vụ:**

1. Liệt kê những phiên bản/baseline cần thu thập trước khi đánh giá.
2. Tìm các tài liệu chính thức liên quan đến Web Flow đích và các bản trung gian.
3. Chọn ít nhất ba mục trong release notes cần đối chiếu với ứng dụng.
4. Tạo ba kịch bản kiểm thử để chứng minh hệ thống có thể resume flow sau nâng cấp.
5. Nêu điều kiện để chấp nhận hoặc chặn PR thay dependency.

**Gợi ý lời giải:**

- Cần version resolved của Spring Web Flow, Spring Framework/Boot nếu có, JDK, Servlet/container, Spring Security nếu dùng, và cách lưu session/repository ở hai node.
- Đọc release/tag tương ứng, migration guide và ghi các thay đổi từ dòng hiện tại đến đích; đối chiếu tài liệu tích hợp Spring MVC và những thư viện hạ tầng liên quan.
- Chú ý baseline/binary compatibility, FlowExecutor/repository/snapshot, URL/execution parameter, binding/validation và security.
- Thử: (a) tạo flow rồi submit từ cùng một node; (b) chuyển qua node khác khi dùng session strategy thực; (c) dùng Back/Refresh hoặc key cũ sau timeout và kiểm tra phản hồi an toàn.
- Chỉ chấp nhận khi tổ hợp dependency/runtime có căn cứ tương thích, build và các flow nghiệp vụ chính qua regression test, các breaking change đã được xử lý, và rollback có thể thực hiện.

**Điểm cốt lõi:** Release notes là đầu vào cho một quyết định kỹ thuật có thể kiểm chứng. Đọc đúng dòng đích, kiểm tra toàn bộ tổ hợp Spring và chuyển từng thay đổi có ảnh hưởng thành test giúp nâng cấp Spring Web Flow có kiểm soát, nhất là với ứng dụng cũ đang sử dụng form, session, MVC integration và các quy trình nhiều bước.
