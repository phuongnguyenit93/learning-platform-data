# Cấu hình và phiên bản

## Đọc appendix để phát hiện thuộc tính deprecated

Khi nâng cấp Spring Modulith, một cấu hình YAML vẫn có thể trông hợp lệ dù tên thuộc tính đã cũ. Nếu chỉ đọc ví dụ trong một bài hướng dẫn, nhóm dễ bỏ sót thuộc tính đã được thay thế hoặc khác biệt giữa các phiên bản. Appendix của tài liệu Spring Modulith là nơi tra cứu tập trung để kiểm tra khả năng tương thích, thuộc tính cấu hình, các module thư viện và thông tin migration.

Mục tiêu của việc đọc appendix là xác định **thuộc tính nào đang được phiên bản dự án hỗ trợ, thuộc tính nào đã deprecated, thuộc tính thay thế là gì và cần xác minh điều gì trước khi xóa cấu hình cũ**. Không nên nâng cấp bằng cách đổi tên thuộc tính hàng loạt mà không đối chiếu phiên bản và ý nghĩa của cấu hình.

### 1. Appendix chứa những thông tin nào?

Appendix của Spring Modulith được chia thành các phần phục vụ những câu hỏi khác nhau. Tên và số thứ tự appendix có thể thay đổi theo phiên bản tài liệu, vì vậy hãy đọc mục lục của đúng trang phiên bản dự án đang dùng.

| Phần | Nội dung | Câu hỏi cần trả lời |
|---|---|---|
| Spring Boot Compatibility | Ma trận phiên bản Spring Modulith, Spring Boot và jMolecules | Phiên bản thư viện đang chọn có tương thích với nền tảng không? |
| Spring Modulith Configuration Properties | Danh sách property, giá trị mặc định và mô tả | Property có tên chính xác là gì, giá trị mặc định và phạm vi ảnh hưởng ra sao? |
| Spring Modulith modules | Starter và JAR thành phần cùng scope điển hình | Nên dùng starter hay dependency riêng, và dependency thuộc compile, runtime hay test? |
| Event publication registry schemas | Schema cần có cho các database được hỗ trợ | Cấu trúc bảng hoặc collection có phù hợp với cấu hình hiện tại không? |
| Migration information | Thay đổi tên API, package hoặc cách sử dụng từ phiên bản trước | Khi nâng cấp cần đổi mã nguồn hoặc cấu hình nào? |

Trong bài này, phần Configuration Properties là trọng tâm để phát hiện deprecated property. Các phần còn lại giúp xác nhận rằng property được đọc trong đúng bối cảnh phiên bản và module thư viện.

### 2. Luôn mở appendix theo đúng phiên bản

Trang tài liệu mặc định thường trỏ đến phiên bản mới nhất. Trong khi đó, dự án có thể đang dùng một nhánh Spring Modulith cũ hơn. Một property được đánh dấu deprecated trong tài liệu 1.4 có thể đã không còn xuất hiện trong bảng property của tài liệu 2.2; ngược lại, property mới trong phiên bản hiện tại có thể chưa tồn tại trong phiên bản cũ.

Trước khi tra cứu, xác định phiên bản thực tế từ dependency management của dự án:

```kotlin
dependencies {
    implementation(platform(
        "org.springframework.modulith:spring-modulith-bom:<modulith-version>"
    ))

    implementation("org.springframework.modulith:spring-modulith-starter-core")
}
```

Nếu dự án dùng Spring Boot dependency management hoặc một version catalog, hãy kiểm tra nơi phiên bản Spring Modulith được quản lý ở đó. Đừng suy ra phiên bản chỉ từ tên starter hoặc từ trang tài liệu đang mở.

Sau đó mở appendix tương ứng với dòng phiên bản. Đọc ma trận Spring Boot Compatibility trước để kiểm tra nền tảng. Khi phiên bản Spring Modulith được quản lý gián tiếp, hãy kiểm tra dependency tree hoặc dependency insight để biết phiên bản đã được phân giải thực tế.

### 3. Tìm dấu hiệu deprecated trong bảng Configuration Properties

Ở phần Configuration Properties, mỗi dòng thường có tên property đầy đủ, giá trị mặc định và mô tả. Khi đọc bảng, tìm những cụm từ như:

- `Deprecated as of ...`: property đã bị đánh dấu deprecated từ phiên bản được nêu.
- `Prefer ...`: tài liệu chỉ ra property thay thế được khuyến nghị.
- `Use ... instead` hoặc `replaced by ...`: tên mới hoặc API mới cần chuyển sang.
- `Removed in ...`: dấu hiệu property đã bị loại bỏ ở phiên bản cụ thể, nếu tài liệu hoặc migration notes ghi rõ.

Ví dụ trong appendix Spring Modulith 1.4, thuộc tính sau được đánh dấu deprecated từ 1.3:

```properties
spring.modulith.republish-outstanding-events-on-restart=true
```

Mô tả chỉ rõ property thay thế là:

```properties
spring.modulith.events.republish-outstanding-events-on-restart=true
```

Đây là thay đổi vị trí của property trong namespace `events`. Giá trị `true` vẫn biểu đạt mong muốn republish các event publication còn outstanding khi ứng dụng khởi động lại. Tài liệu cũng lưu ý không nên bật tùy chọn này một cách thiếu cân nhắc trong môi trường nhiều instance, vì instance khác có thể vẫn đang xử lý event.

Trong YAML, cấu hình cần được chuyển như sau:

```yaml
# Tên cũ: deprecated từ Spring Modulith 1.3
spring:
  modulith:
    republish-outstanding-events-on-restart: true
```

```yaml
# Tên mới được khuyến nghị
spring:
  modulith:
    events:
      republish-outstanding-events-on-restart: true
```

Khi chuyển đổi, xóa cấu hình cũ sau khi đã xác nhận cấu hình mới được bind. Tránh để cả hai tên cùng tồn tại trong nhiều file hoặc nhiều profile vì người bảo trì sau này sẽ khó xác định property nào là nguồn cấu hình chính.

### 4. Đối chiếu thay đổi giữa các appendix

Một ví dụ tốt về cách đọc lịch sử là so sánh appendix 1.4 với appendix hiện tại. Tài liệu 1.4 ghi rõ property cũ `spring.modulith.republish-outstanding-events-on-restart` deprecated từ 1.3 và khuyến nghị property mới có tiền tố `events`. Appendix 2.2 liệt kê property mới trong bảng cấu hình chính.

| Phiên bản tài liệu | Cách thể hiện | Cách diễn giải |
|---|---|---|
| 1.2 | Property cũ được liệt kê như property cấu hình | Tên cũ vẫn là tên được tài liệu phiên bản này công bố |
| 1.4 | Property cũ có ghi chú deprecated as of 1.3 và nêu replacement | Nên chuyển cấu hình sang tên mới khi nâng cấp |
| 2.2 | Bảng cấu hình liệt kê property mới | Dùng tên mới làm cấu hình chuẩn; kiểm tra metadata và migration notes nếu cần xác định khả năng tương thích của alias cũ |

**Không kết luận rằng property đã bị xóa chỉ vì nó không còn xuất hiện trong bảng của phiên bản mới.** Bảng appendix là tài liệu tham khảo về cấu hình được công bố, không phải lúc nào cũng mô tả đầy đủ mọi alias tương thích ngược. Hãy kiểm tra thêm configuration metadata, API constant hoặc release notes trước khi khẳng định property cũ không còn được bind.

Điều này đặc biệt quan trọng với property đã deprecated: một phiên bản có thể tiếp tục nhận tên cũ để hỗ trợ migration, dù tài liệu chỉ khuyến nghị tên mới. Việc giữ alias tương thích không có nghĩa nhóm nên tiếp tục sử dụng alias đó trong cấu hình mới.

### 5. Kiểm tra configuration metadata của Spring Boot

Spring Boot hỗ trợ metadata mô tả các property được cung cấp bởi thư viện. Metadata thường được đóng gói trong `META-INF/spring-configuration-metadata.json`. Công cụ IDE có thể đọc metadata để gợi ý property, kiểu dữ liệu, giá trị mặc định và cảnh báo deprecation.

Một property deprecated có thể có metadata dạng:

```json
{
  "name": "spring.modulith.republish-outstanding-events-on-restart",
  "type": "java.lang.Boolean",
  "deprecation": {
    "level": "warning",
    "reason": "Use the events-specific property instead.",
    "replacement": "spring.modulith.events.republish-outstanding-events-on-restart",
    "since": "1.3"
  }
}
```

Đây là ví dụ minh họa cấu trúc metadata deprecation của Spring Boot; nội dung thực tế cần đọc từ JAR và phiên bản dependency của dự án.

Các trường metadata quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `level` | `warning` hoặc `error` |
| `reason` | Lý do property bị deprecated |
| `replacement` | Tên property thay thế đầy đủ, nếu có |
| `since` | Phiên bản bắt đầu deprecated, nếu được cung cấp |

`warning` có nghĩa property vẫn được bind nhưng nên được thay thế. `error` có nghĩa property không còn được quản lý và không được bind. Do đó, cảnh báo deprecated không tự động đồng nghĩa với việc ứng dụng đã ngừng hoạt động; nó báo rằng cấu hình cần được chuyển đổi trước khi alias bị loại bỏ.

Khi IDE không hiển thị cảnh báo, hãy kiểm tra metadata trong dependency JAR thực tế. Một thư viện có thể không cung cấp đầy đủ metadata cho tất cả property; khi đó cần đối chiếu thêm appendix, release notes và mã nguồn của đúng phiên bản.

### 6. Quy trình audit property trước khi nâng cấp

Có thể thực hiện một lượt audit ngắn trước mỗi lần nâng cấp Spring Modulith:

1. Ghi nhận phiên bản đang dùng và phiên bản đích từ BOM hoặc dependency management.
2. Mở Appendix A của cả hai phiên bản để xác nhận Spring Boot compatibility.
3. Mở Appendix B và tìm toàn bộ property có tiền tố `spring.modulith` đang được ứng dụng cấu hình.
4. Đánh dấu những dòng có ghi chú deprecated, replacement hoặc thay đổi default value.
5. Đối chiếu metadata trong JAR và migration notes để xác định property còn được bind hay đã bị loại bỏ.
6. Chuyển cấu hình sang tên mới, cập nhật tài liệu vận hành và xóa alias cũ.
7. Kiểm tra cấu hình ở tất cả profile, file YAML, biến môi trường và tham số command line.
8. Chạy kiểm tra khởi động hoặc integration test để xác nhận property mới được bind và hành vi thực tế vẫn đúng.

Ví dụ, tìm các property Spring Modulith trong thư mục cấu hình bằng ripgrep:

```bash
rg -n "spring\.modulith" src/main/resources src/test/resources
```

Sau đó kiểm tra các file `application-*.yml`, `application-*.yaml` và `application-*.properties`, cũng như cấu hình được truyền qua môi trường triển khai. Một property có thể đã được đổi trong `application.yml` nhưng vẫn còn tên cũ trong profile production hoặc Helm values.

Nên tạo một bảng audit có trạng thái rõ ràng:

| Property hiện tại | Trạng thái theo appendix | Replacement | Hành động |
|---|---|---|---|
| `spring.modulith.republish-outstanding-events-on-restart` | Deprecated as of 1.3 | `spring.modulith.events.republish-outstanding-events-on-restart` | Chuyển sang tên mới và kiểm tra hành vi khi restart |
| `spring.modulith.events.republish-outstanding-events-on-restart` | Property được công bố trong phiên bản mới | — | Dùng làm tên cấu hình chuẩn |

### 7. Xác minh sau khi đổi property

Đổi tên property là một thay đổi cấu hình runtime. Test chỉ kiểm tra file YAML tồn tại chưa đủ; cần xác minh Spring Boot đã bind giá trị và thành phần sử dụng property nhận đúng hành vi.

Với property có thể bind qua `@ConfigurationProperties`, có thể viết test context để kiểm tra giá trị sau khi application context khởi tạo. Với property điều khiển hành vi event publication, nên kiểm tra hành vi tương ứng trong một integration test: event publication đang outstanding có được xử lý theo cấu hình mới hay không, và các listener hoặc registry có hoạt động đúng không.

Ví dụ kiểm tra một property application-specific bằng `@SpringBootTest`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest(properties = {
    "spring.modulith.events.republish-outstanding-events-on-restart=true"
})
class EventConfigurationTests {

    @Autowired
    Environment environment;

    @Test
    void usesTheCurrentPropertyName() {
        assertThat(environment.getProperty(
            "spring.modulith.events.republish-outstanding-events-on-restart",
            Boolean.class)).isTrue();
    }
}
```

Test trên xác nhận Spring Environment nhìn thấy property với tên mới. Nó chưa chứng minh toàn bộ cơ chế republish hoạt động đúng; hành vi đó cần integration test có event publication registry và listener phù hợp. Khi kiểm tra property của thư viện, ưu tiên assertion về hành vi mà property điều khiển thay vì chỉ đọc lại cùng chuỗi từ Environment.

### 8. Đọc giá trị mặc định và mô tả cùng với deprecation

Một property không deprecated vẫn có thể thay đổi default value hoặc ý nghĩa giữa các phiên bản. Khi đọc Appendix B, hãy so sánh cả ba thành phần:

- Tên property và namespace.
- Default value.
- Mô tả hành vi và những giới hạn vận hành.

Ví dụ, `spring.modulith.events.republish-outstanding-events-on-restart` có default `false`. Việc chuyển từ tên cũ sang tên mới không phải lý do để tự động bật property. Chỉ bật khi hệ thống có nhu cầu khôi phục publication còn outstanding và đã đánh giá rủi ro triển khai nhiều instance.

Tương tự, property `spring.modulith.runtime.verification-enabled` có default `false` và yêu cầu artifact `spring-modulith-runtime` trên classpath. Chỉ thêm property vào YAML mà thiếu runtime dependency sẽ không tạo ra cơ chế kiểm tra lúc startup như mong muốn.

### 9. Những lỗi thường gặp khi đọc appendix

| Lỗi | Hệ quả | Cách tránh |
|---|---|---|
| Đọc appendix của latest thay vì phiên bản dự án | Dùng property chưa có trong dependency hiện tại | Xác định phiên bản từ dependency management trước |
| Chỉ tìm tên property, bỏ qua mô tả | Bỏ sót deprecation hoặc thay đổi default | Đọc cả cột Description và phần migration |
| Coi deprecated đồng nghĩa đã bị xóa | Tạo giả định sai về khả năng bind | Kiểm tra deprecation level và metadata thực tế |
| Thấy property biến mất rồi kết luận chắc chắn đã bị loại bỏ | Có thể bỏ qua alias tương thích ngược | Kiểm tra release notes, metadata và API của đúng phiên bản |
| Đổi tên ở một file cấu hình duy nhất | Profile khác vẫn dùng property cũ | Audit tất cả nguồn cấu hình và môi trường triển khai |
| Giữ cả property cũ và mới | Khó xác định nguồn cấu hình có hiệu lực | Chỉ giữ tên chuẩn sau khi migration được xác minh |
| Không đọc default value | Hành vi runtime thay đổi dù tên property không đổi | So sánh default và viết test cho hành vi quan trọng |

### 10. Checklist trước khi hoàn tất nâng cấp

- [ ] Phiên bản Spring Modulith đang dùng và phiên bản đích đã được xác định.
- [ ] Appendix của cả hai phiên bản đã được đối chiếu.
- [ ] Các property `spring.modulith.*` đang sử dụng đã được lập danh sách.
- [ ] Property deprecated đã có replacement hoặc quyết định xử lý rõ ràng.
- [ ] Metadata deprecation đã được kiểm tra khi cần xác định warning hay error.
- [ ] Các file profile, biến môi trường và cấu hình triển khai đã được audit.
- [ ] Default value và ý nghĩa của property đã được so sánh.
- [ ] Test xác nhận property mới được bind và hành vi runtime quan trọng vẫn đúng.
- [ ] Cấu hình cũ và ghi chú migration đã được loại bỏ hoặc cập nhật.

Đọc appendix là một bước nhỏ nhưng quan trọng trong mỗi lần nâng cấp. Khi kết hợp bảng compatibility, danh sách configuration properties, metadata deprecation và migration notes, nhóm có thể phát hiện cấu hình lỗi thời sớm, chuyển sang tên property được hỗ trợ và giữ hành vi của ứng dụng có thể dự đoán.

### Tài liệu tham khảo

- [Spring Modulith — Appendix (latest stable)](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith 1.4 — Appendix](https://docs.spring.io/spring-modulith/reference/1.4-SNAPSHOT/appendix.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Boot — Configuration Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
