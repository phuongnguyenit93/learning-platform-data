# Kế thừa PropertySource và profile trong hệ phân cấp

Bài học thuộc chương **Phân cấp context** của module **SPRING_CLOUD_CORE**. Trong ứng dụng Spring có nhiều `ApplicationContext` liên kết theo quan hệ parent–child, việc một context tra cứu được cấu hình hoặc bean của context khác phụ thuộc vào cách thiết lập hierarchy và `Environment` của từng context.

Hai khái niệm cần tách biệt:

- **Phân cấp ApplicationContext:** quy định phạm vi bean và quan hệ tra cứu bean giữa parent với child.
- **Phân cấp Environment:** quy định cách các `PropertySource` và profile được đưa vào môi trường của context để phân giải cấu hình.

Một child context thường có thể kế thừa property sources và active/default profiles từ parent thông qua cơ chế merge. PropertySource cục bộ của child được ưu tiên hơn source của parent. Tuy nhiên, nếu hai source trùng tên, source của child được giữ và source cùng tên của parent bị loại khỏi child; Spring không hợp nhất từng key trong hai source đó. Profile cũng được hợp nhất theo tập tên profile, không phải kế thừa nguyên trạng mọi bean hay mọi tài liệu cấu hình.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích parent–child ApplicationContext và phân biệt nó với quan hệ giữa các Environment.
2. Mô tả cách `ConfigurableEnvironment.merge(parent)` đưa property sources, active profiles và default profiles từ parent vào child.
3. Xác định giá trị property thắng khi child và parent cùng khai báo một khóa.
4. Phát hiện xung đột khi hai PropertySource khác nhau dùng cùng tên.
5. Giải thích active/default profiles được hợp nhất, loại trùng và cách `setActiveProfiles` khác `addActiveProfile`.
6. Phân biệt profile của parent, child và sibling context; biết khi nào chúng dùng chung Environment.
7. Hiểu cách Spring Cloud bootstrap context và Spring Cloud Config đưa remote PropertySource vào hierarchy.
8. Phân biệt legacy bootstrap với Spring Boot Config Data import hiện đại.
9. Thiết kế test kiểm chứng property resolution, profile selection và giới hạn của việc merge.

## 2. ApplicationContext hierarchy là gì?

Một ứng dụng có thể tạo nhiều Spring container thay vì chỉ một context duy nhất. Một context có thể được gắn làm **parent** của context khác:

~~~mermaid
flowchart TD
    P["Parent ApplicationContext"] --> C1["Child context: order"]
    P --> C2["Child context: inventory"]
    C1 --> G1["Bean riêng của order"]
    C2 --> G2["Bean riêng của inventory"]
    P --> PB["Bean dùng chung ở parent"]
~~~

Một số đặc điểm cơ bản:

- Child có thể tra cứu bean được định nghĩa trong chính nó và bean có thể truy cập từ parent.
- Parent không tra cứu ngược bean chỉ tồn tại trong child.
- Child có thể định nghĩa bean cùng tên để che khuất bean cùng tên ở parent trong quá trình tra cứu từ child.
- Sibling không tự nhìn thấy bean riêng của nhau; chúng có thể dùng chung bean được đặt ở parent.
- Mỗi context có vòng đời riêng: refresh, close và quản lý bean riêng.

Ví dụ, parent chứa bean dùng chung như client HTTP hoặc thành phần hạ tầng. Child của `order-service` và `inventory-service` có thể định nghĩa bean nghiệp vụ riêng, đồng thời tra cứu bean hạ tầng từ parent.

**Bean visibility không đồng nghĩa với property inheritance.** Việc child nhìn thấy bean của parent không tự nói lên thứ tự ưu tiên cấu hình. Muốn hiểu cấu hình, cần kiểm tra Environment của context đó.

## 3. Environment và PropertySource trong một context

### 3.1. Environment là nơi phân giải property

`Environment` là abstraction để đọc property và profile. Một Environment có tập hợp các `PropertySource` được sắp xếp theo thứ tự tìm kiếm. Khi nhiều source cùng chứa một khóa, source được tìm thấy trước sẽ cung cấp giá trị.

Ví dụ:

~~~java
String region = environment.getProperty("app.region");
~~~

Giá trị trả về không chỉ phụ thuộc khóa có tồn tại mà còn phụ thuộc:

- Source nào chứa khóa đó.
- Source được đặt ở vị trí nào trong danh sách.
- Source có bị thay thế hoặc loại bỏ hay không.
- Environment của context đang được truy vấn là Environment riêng hay Environment được chia sẻ.

### 3.2. PropertySource có tên

Mỗi PropertySource có tên để nhận diện trong tập nguồn. Ví dụ:

~~~java
new MapPropertySource(
    "parent-defaults",
    Map.of("app.region", "ap-southeast")
);
~~~

Tên source không phải tên khóa property. Hai source có tên khác nhau có thể cùng chứa `app.region`; khi đó thứ tự trong danh sách quyết định giá trị thắng.

Tên source còn quan trọng khi merge parent và child. Nếu source của child trùng tên với source của parent, Spring giữ source child và bỏ source parent có tên trùng. Đây là thay thế source theo tên, không phải ghép hai map theo từng khóa.

### 3.3. Environment riêng và Environment dùng chung

Có hai mô hình cần phân biệt:

| Mô hình | Đặc điểm | Hệ quả |
| --- | --- | --- |
| **Environment riêng cho từng context** | Parent và child có Environment riêng; child có thể merge Environment của parent. | Có thể thêm cấu hình cục bộ và profile riêng cho child. |
| **Environment dùng chung** | Nhiều context tham chiếu cùng một đối tượng Environment. | Thay đổi PropertySource/profile trên đối tượng đó có thể ảnh hưởng các context cùng dùng; mức cô lập thấp hơn. |

`SpringApplicationBuilder` có thể được cấu hình để chia sẻ Environment trong hierarchy, nhưng đó không phải mặc định. Không nên giả định hai sibling luôn có cùng active profiles hoặc PropertySource chỉ vì chúng có chung parent.

Nếu cần mỗi child có cấu hình khác nhau, hãy giữ Environment riêng và merge có chủ đích. Nếu cần cùng một bộ cấu hình thay đổi đồng bộ, có thể chọn chia sẻ Environment hoặc một cơ chế phát tán cấu hình, nhưng phải hiểu tác động lên tất cả context tham gia.

## 4. Cách ConfigurableEnvironment.merge(parent) hoạt động

Spring Framework cung cấp `ConfigurableEnvironment.merge(ConfigurableEnvironment parent)`. Khi merge:

1. Active profiles của parent được thêm vào tập active profiles của child.
2. Default profiles của parent được thêm vào tập default profiles của child.
3. PropertySource của parent được append vào danh sách PropertySource của child.
4. Profile trùng tên được loại trùng.
5. Nếu source có cùng tên xuất hiện ở cả parent và child, source child được giữ, source parent bị bỏ.
6. Environment parent không bị thay đổi.
7. Với Environment riêng, các thay đổi được thực hiện trên parent sau thời điểm merge không tự động được đồng bộ sang child; cần cập nhật/merge lại theo lifecycle phù hợp hoặc dùng chung Environment nếu đó là chủ đích.

Vì property sources của parent được append vào danh sách child, các source cục bộ đã có ở child thường được tìm trước và có ưu tiên cao hơn source được kế thừa.

### 4.1. Ví dụ parent và child có source khác tên

Parent:

~~~java
ConfigurableEnvironment parent = new StandardEnvironment();

parent.getPropertySources().addFirst(
    new MapPropertySource("parent-config", Map.of(
        "app.region", "ap-southeast",
        "app.timeout", "2s",
        "app.parent-only", "parent-value"
    ))
);

parent.setActiveProfiles("common", "production");
~~~

Child:

~~~java
ConfigurableEnvironment child = new StandardEnvironment();

child.getPropertySources().addFirst(
    new MapPropertySource("child-config", Map.of(
        "app.region", "eu-west",
        "app.child-only", "child-value"
    ))
);

child.setActiveProfiles("worker");
child.merge(parent);
~~~

Kết quả tra cứu trong child:

| Khóa | Giá trị | Nguồn thắng |
| --- | --- | --- |
| `app.region` | `eu-west` | `child-config` |
| `app.timeout` | `2s` | `parent-config` được kế thừa |
| `app.parent-only` | `parent-value` | `parent-config` được kế thừa |
| `app.child-only` | `child-value` | `child-config` |

Active profiles trong child gồm `worker`, `common` và `production`. Profile parent được thêm vào tập của child; profile child vẫn được giữ.

### 4.2. Source trùng tên: child thay thế parent source

Giả sử parent có:

~~~java
parent.getPropertySources().addFirst(
    new MapPropertySource("shared-config", Map.of(
        "app.color", "blue",
        "app.parent-only", "visible-in-parent"
    ))
);
~~~

Child có:

~~~java
child.getPropertySources().addFirst(
    new MapPropertySource("shared-config", Map.of(
        "app.color", "green",
        "app.child-only", "visible-in-child"
    ))
);
~~~

Sau `child.merge(parent)`, source `shared-config` của child được giữ. Source `shared-config` của parent không được đưa vào danh sách child vì trùng tên.

Kết quả:

- `app.color` trong child là `green`.
- `app.child-only` trong child là `visible-in-child`.
- `app.parent-only` không được lấy từ source parent đã bị loại khỏi child.
- Parent vẫn giữ source ban đầu và khi truy vấn trực tiếp ở parent, `app.color` vẫn là `blue`.

Đây là điểm rất dễ gây lỗi. Nếu muốn kế thừa các key parent mà vẫn cho child override một phần, hãy dùng tên PropertySource khác nhau, ví dụ `parent-config` và `child-config`, hoặc chủ động tạo một source đã hợp nhất trước khi đưa vào Environment.

### 4.3. Thứ tự merge và precedence

Có thể hình dung danh sách source sau merge:

~~~text
Environment của child
  1. child-config          (ưu tiên cao hơn)
  2. child-local-defaults
  3. parent-config         (được append từ parent)
  4. parent-defaults
  5. các source mặc định khác tùy Environment
~~~

Đây là sơ đồ minh họa, không phải danh sách cố định cho mọi Spring Boot application. Thứ tự thực tế phụ thuộc những source nào được tạo và cách chúng được thêm vào.

Không nên chỉ dựa vào tên source để suy ra precedence. Khi có xung đột, kiểm tra thứ tự thực tế trong `environment.getPropertySources()` và giá trị trả về từ `getProperty()`.

## 5. Kế thừa active profiles và default profiles

### 5.1. Profile được merge thành tập tên

Profile điều khiển các bean hoặc tài liệu cấu hình được kích hoạt. Khi Environment child merge parent, active profiles và default profiles từ parent được append vào tập tương ứng của child; tên trùng được loại bỏ.

Ví dụ:

| Context | Active profiles trước merge |
| --- | --- |
| Parent | `common`, `production` |
| Child | `worker`, `production` |
| Child sau merge | `worker`, `production`, `common` |

`production` chỉ xuất hiện một lần. Profile `common` được kế thừa từ parent, còn `worker` là profile cục bộ của child.

Profile không phải PropertySource. Nó là trạng thái của Environment được dùng khi đánh giá `@Profile` và khi lựa chọn các tài liệu cấu hình theo profile.

### 5.2. setActiveProfiles khác addActiveProfile

Hai API có hành vi khác nhau:

- `setActiveProfiles("worker")` thay thế tập active profiles hiện tại bằng tập được truyền.
- `addActiveProfile("worker")` thêm một profile vào tập hiện tại và giữ các profile đang có.

Nếu child đã merge parent rồi gọi `setActiveProfiles("worker")`, các profile parent đã merge có thể bị loại khỏi tập active của child. Nếu mục tiêu là thêm profile cục bộ mà vẫn giữ profile kế thừa, dùng `addActiveProfile` hoặc cấu hình profile theo cách không thay thế tập hiện tại.

Ví dụ:

~~~java
child.merge(parent);

// Thêm profile mà vẫn giữ profile đã merge
child.addActiveProfile("worker");
~~~

Không nên gọi `setActiveProfiles` sau merge nếu chưa chủ ý thay thế toàn bộ tập profile.

### 5.3. Default profile không phải active profile thông thường

Default profile được dùng khi không có active profile phù hợp. Khi merge, default profiles từ parent được thêm vào default profiles của child và loại trùng.

Nếu child có active profile, default profile không được xem như một active profile bổ sung. Hãy kiểm tra riêng:

~~~java
environment.getActiveProfiles();
environment.getDefaultProfiles();
~~~

Điều này giúp tránh nhầm lẫn khi một bean có `@Profile("default")` không được đăng ký dù parent có default profile, bởi child đang có active profile khác.

## 6. Profile ảnh hưởng tới bean và tài liệu cấu hình thế nào?

### 6.1. @Profile được đánh giá trong context chứa bean

Ví dụ:

~~~java
@Configuration
@Profile("production")
class ProductionConfiguration {
    @Bean
    PaymentPolicy paymentPolicy() {
        return new ProductionPaymentPolicy();
    }
}
~~~

Bean này được đăng ký khi cấu hình được xử lý trong context có active profile `production`.

Nếu parent context đã refresh với profile `production`, bean trong parent được tạo theo profile của parent. Sau đó child có thêm profile `worker` không làm parent quét lại cấu hình hay tạo lại bean theo profile của child.

Ngược lại, child có thể nhìn thấy bean parent đã tạo nếu bean đó được expose trong hierarchy. Nếu child cần một implementation khác, hãy định nghĩa bean riêng trong child và thiết kế rõ cách override/lookup.

### 6.2. Profile-specific configuration file

Spring Boot có thể nạp các file như:

~~~text
application.yml
application-common.yml
application-production.yml
application-worker.yml
~~~

Profile đang hoạt động trong Environment ảnh hưởng đến việc lựa chọn tài liệu cấu hình profile-specific. Tuy nhiên, file nào được nạp còn phụ thuộc Config Data locations, cách khởi chạy từng context và property sources mà context đó sở hữu.

Trong hierarchy có Environment riêng:

- Parent có thể nạp tài liệu cấu hình phù hợp với profile của parent.
- Child có thể nạp tài liệu cấu hình phù hợp với profile của child.
- Child sau khi merge còn có thể tra cứu PropertySource được kế thừa từ parent.
- Việc child nhìn thấy property của parent không có nghĩa child tự nạp lại mọi file của parent hoặc parent nạp file theo profile của child.

Hãy phân biệt **kế thừa PropertySource đã tồn tại** với **quy trình Config Data loading của từng SpringApplication**.

### 6.3. spring.profiles.include và profile groups

Spring Boot có các cơ chế bổ sung profile:

- `spring.profiles.include` thêm profile vào tập profile đang hoạt động.
- `spring.profiles.group` cho phép kích hoạt một nhóm profile bằng tên logic.
- `spring.profiles.active` chỉ định tập profile active theo property precedence hoặc API.

Các thuộc tính này được xử lý trong quy trình cấu hình Spring Boot và không thay thế quy tắc `ConfigurableEnvironment.merge(parent)`. Đặc biệt, `spring.profiles.active`, `spring.profiles.include` và `spring.profiles.group` chỉ được khai báo trong tài liệu cấu hình không phải profile-specific document theo quy tắc Spring Boot.

Không nên nhầm việc profile được include/group trong một context với việc bean của parent được kích hoạt lại. Mỗi context vẫn có quá trình đăng ký bean riêng.

## 7. Tạo hierarchy bằng SpringApplicationBuilder

`SpringApplicationBuilder` cung cấp API để tạo parent, child và sibling contexts.

Ví dụ minh họa:

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
    .child(OrderConfiguration.class)
    .run(args);
~~~

Parent có thể chứa các bean dùng chung. Child chứa bean nghiệp vụ của order. Khi builder tạo hierarchy, Environment của các context được xử lý theo cơ chế hierarchy; cấu hình chia sẻ cùng một Environment phải được thực hiện rõ ràng, không mặc định rằng toàn bộ context luôn dùng cùng một object Environment.

Có thể mở rộng thành sibling:

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
    .child(OrderConfiguration.class)
    .sibling(InventoryConfiguration.class)
    .run(args);
~~~

Cấu trúc API cụ thể cần được kiểm tra theo phiên bản Spring Boot. Trong ứng dụng thực tế, cần kiểm tra từng context được tạo ra, active profiles, PropertySource và bean visibility thay vì chỉ nhìn builder chain.

### 7.1. Khi nào nên dùng parent-child?

Một hierarchy có ích khi các context cần:

- Chia sẻ một số bean hạ tầng ở parent.
- Có bean nghiệp vụ hoặc cấu hình cục bộ riêng.
- Có vòng đời riêng cho từng nhóm thành phần.
- Có thể chọn profile hoặc PropertySource riêng cho child.
- Phân tách cấu hình theo logical application trong một JVM.

Không nên tạo hierarchy chỉ để “dùng chung cấu hình” nếu một Environment duy nhất hoặc một configuration object đơn giản đã đủ. Hierarchy làm tăng độ phức tạp về lifecycle, bean visibility, profile và precedence.

## 8. Spring Cloud bootstrap context và PropertySource hierarchy

### 8.1. Legacy bootstrap context

Trong chế độ bootstrap truyền thống của Spring Cloud, một bootstrap context được tạo làm parent của main application context. Bootstrap context thường dùng để tải cấu hình ngoài và thực hiện các xử lý trước khi main context hoàn tất khởi động.

Trong cơ chế này:

- Bootstrap context và main context có quan hệ parent–child.
- Một Environment có thể được chia sẻ theo cơ chế bootstrap.
- Remote property source (ví dụ từ Spring Cloud Config Server) có thể được thêm vào với mức ưu tiên cao.
- `bootstrap.yml` là convention cho cấu hình giai đoạn bootstrap; nó không đồng nghĩa với remote property source tên `bootstrap`.
- Các giá trị trong `bootstrap.yml` có thể được dùng làm cấu hình mặc định cho bootstrap context và có precedence thấp hơn cấu hình ứng dụng thông thường.
- Mỗi context trong hierarchy có thể có bootstrap property source riêng; cần tránh vô tình đẩy cấu hình cục bộ của parent xuống mọi descendant.

Chế độ bootstrap legacy phải được bật theo hướng dẫn phiên bản, ví dụ bằng `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true` được cung cấp đủ sớm qua system property/environment. Không giả định bootstrap context luôn tự xuất hiện trong mọi ứng dụng Spring Cloud.

### 8.2. Remote PropertySource và override

Với Spring Cloud Config trong bootstrap mode, remote properties thường được đặt ở vị trí ưu tiên cao và mặc định không cho cấu hình local ghi đè. Nếu muốn local override remote properties, remote property source phải cho phép thông qua `spring.cloud.config.allowOverride=true` được cấu hình từ phía remote server.

Các tùy chọn như:

- `spring.cloud.config.overrideNone=true`: cho phép local property source override remote theo chính sách tương ứng.
- `spring.cloud.config.overrideSystemProperties=false`: giới hạn loại local source được phép override remote.

Đây là quy tắc của Spring Cloud Config remote property source trong chế độ bootstrap, không phải quy tắc tổng quát cho mọi PropertySource hoặc mọi Spring context hierarchy. Hãy kiểm tra release train đang dùng.

### 8.3. Config Data import hiện đại

Với Spring Boot 2.4 trở lên, cách mặc định hiện đại để kết nối Spring Cloud Config Client là Config Data import:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Cách này không cần `bootstrap.yml` cho Config Data import. Remote config được nạp trong quy trình Config Data của Spring Boot.

Phân biệt:

| Cách tích hợp | Cơ chế | File bootstrap |
| --- | --- | --- |
| Config Data import | `spring.config.import=configserver:...` | Không cần `bootstrap.yml` |
| Legacy bootstrap | Bootstrap context parent tải remote properties trước main context | Dùng `bootstrap.yml` hoặc cấu hình bootstrap tương ứng |

Không trộn ví dụ từ hai cơ chế mà không xác định mode đang chạy. Nếu hệ thống dùng legacy bootstrap, hãy kiểm tra cách bootstrap được bật và vị trí property source. Nếu dùng Config Data import, hãy kiểm tra import và thứ tự Config Data trong Environment của ứng dụng.

## 9. Ví dụ cấu hình cho parent và child

Giả sử ứng dụng có parent dùng cấu hình chung và child order có cấu hình riêng.

Parent source:

~~~yaml
app:
  region: ap-southeast
  timeout: 2s
  logging-mode: compact
~~~

Child source:

~~~yaml
app:
  region: eu-west
  service-name: order-service
~~~

Sau khi child merge parent Environment (với source có tên khác nhau), child có thể phân giải:

| Property | Giá trị trong child | Lý do |
| --- | --- | --- |
| `app.region` | `eu-west` | Child source có khóa trùng và được tìm trước. |
| `app.timeout` | `2s` | Child không khai báo; giá trị từ parent còn khả dụng. |
| `app.logging-mode` | `compact` | Child kế thừa property source của parent. |
| `app.service-name` | `order-service` | Property chỉ có ở child. |

Nếu hai source trùng tên, kết quả khác: source parent cùng tên bị loại khỏi danh sách child, nên những khóa chỉ có ở source parent đó không còn được child kế thừa qua source này.

### 9.1. Hai context không nhất thiết có cùng kết quả

Parent vẫn có thể phân giải `app.region=ap-southeast` vì Environment parent không bị sửa khi child merge. Child phân giải `app.region=eu-west` vì source cục bộ của child đứng trước source parent.

Đây là lý do phải kiểm tra Environment theo đúng context. Gọi `environment.getProperty("app.region")` từ bean trong parent và child có thể cho hai kết quả khác nhau.

## 10. Kiểm thử kế thừa PropertySource và profile

Một phép thử tốt nên kiểm tra cả giá trị, danh sách source và profile. Không chỉ assert một property cuối cùng rồi kết luận hierarchy đúng.

### 10.1. Kiểm thử merge cơ bản

Ví dụ JUnit-style:

~~~java
@Test
void childMergesParentPropertiesAndProfiles() {
    ConfigurableEnvironment parent = new StandardEnvironment();
    parent.getPropertySources().addFirst(
        new MapPropertySource("parent", Map.of(
            "app.region", "ap-southeast",
            "app.timeout", "2s"
        ))
    );
    parent.setActiveProfiles("common", "production");

    ConfigurableEnvironment child = new StandardEnvironment();
    child.getPropertySources().addFirst(
        new MapPropertySource("child", Map.of(
            "app.region", "eu-west"
        ))
    );
    child.setActiveProfiles("worker");

    child.merge(parent);

    assertEquals("eu-west", child.getProperty("app.region"));
    assertEquals("2s", child.getProperty("app.timeout"));
    assertTrue(Arrays.asList(child.getActiveProfiles())
        .containsAll(List.of("worker", "common", "production")));
}
~~~

Ví dụ cần JUnit 5, Spring Core và các import Java tương ứng. Mục tiêu là kiểm chứng API Environment merge, không cần khởi động toàn bộ Spring Boot application.

### 10.2. Kiểm thử trùng tên PropertySource

Tạo source tên `shared` trong parent và child, mỗi source có một key riêng. Sau merge, xác minh:

- Key của source child vẫn có.
- Key của source parent trùng tên không xuất hiện trong child.
- Parent vẫn truy vấn được key ban đầu của nó.

Phép thử này giúp phát hiện lỗi cấu hình khó thấy: hai thành phần cùng dùng tên PropertySource chung nhưng lại kỳ vọng các key của hai source được cộng dồn.

### 10.3. Kiểm thử profile và @Profile

Tạo một bean parent có `@Profile("production")` và một bean child có `@Profile("worker")`. Khởi tạo mỗi context với active profiles phù hợp, merge Environment trước khi refresh child, rồi kiểm tra bean được đăng ký trong đúng context.

Cần xác minh:

- Parent có profile production thì bean production được tạo trong parent.
- Child nhận profile worker và profile kế thừa thì bean phù hợp được tạo trong child.
- Thay đổi profile của child sau khi parent đã refresh không làm parent tạo lại bean.
- Nếu Environment dùng chung, thay đổi profile cần được xem xét ở phạm vi tất cả context đang dùng Environment đó.

### 10.4. Ma trận kiểm chứng

| ID | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| H1 | Parent có key, child không có key. | Child đọc được giá trị kế thừa. |
| H2 | Parent và child có cùng key, source tên khác nhau. | Giá trị child thắng. |
| H3 | Parent và child có source cùng tên. | Source child được giữ; source parent cùng tên bị loại khỏi child. |
| H4 | Parent và child có profile trùng nhau. | Profile trùng chỉ xuất hiện một lần sau merge. |
| H5 | Parent và child có profile khác nhau. | Child giữ profile riêng và nhận profile parent. |
| H6 | Gọi setActiveProfiles sau merge. | Tập profile hiện tại bị thay thế theo danh sách truyền vào. |
| H7 | Gọi addActiveProfile sau merge. | Profile mới được thêm, profile hiện tại vẫn giữ. |
| H8 | Parent thay đổi Environment sau merge. | Child Environment riêng không tự đồng bộ thay đổi của parent. |
| H9 | Parent đã refresh, child đổi active profile. | Bean parent không được đăng ký lại theo profile child. |
| H10 | Chia sẻ một Environment cho nhiều context. | Thay đổi trên Environment chung có thể ảnh hưởng các context cùng tham chiếu. |

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Child không đọc được property từ parent. | Child chưa merge Environment, hoặc source parent đã bị loại do trùng tên. | Kiểm tra hierarchy và tên PropertySource. |
| Child vẫn nhận giá trị parent dù đã khai báo local. | Source child nằm sau source parent hoặc child không dùng Environment dự kiến. | Kiểm tra thứ tự source trong child Environment. |
| Một số key parent biến mất sau merge. | Source parent và child trùng tên nên source parent bị bỏ toàn bộ. | Đặt tên source khác nhau hoặc tạo source hợp nhất có chủ đích. |
| Profile parent không xuất hiện trong child. | Child đã gọi setActiveProfiles sau merge hoặc merge chưa xảy ra. | Kiểm tra thời điểm merge và cách thiết lập profile. |
| Profile parent có trong child nhưng bean parent không thay đổi. | Bean parent đã được đăng ký trong parent theo profile riêng của parent. | Kiểm tra context sở hữu bean và thời điểm refresh. |
| Sibling có profile khác nhau. | Mỗi sibling có Environment riêng; đây là hành vi có thể mong đợi. | Kiểm tra Environment riêng hay shared. |
| Parent thay đổi property nhưng child không đổi. | Environment child đã merge trước đó và không tự theo dõi mọi thay đổi của parent. | Cập nhật child có chủ đích, merge lại trong lifecycle phù hợp hoặc dùng Environment chung nếu thực sự cần. |
| Cấu hình remote ghi đè local. | Remote PropertySource có precedence cao hoặc override policy không cho local ghi đè. | Kiểm tra bootstrap/config data mode và quyền override phía Config Server. |
| Ứng dụng không có bootstrap context như tài liệu cũ. | Đang dùng Config Data import hoặc chưa bật legacy bootstrap. | Kiểm tra `spring.config.import` và cơ chế bootstrap thực tế. |

## 12. Nguyên tắc thiết kế hierarchy dễ bảo trì

1. **Giữ tên PropertySource có ý nghĩa và duy nhất theo phạm vi.** Tránh nhiều module tự tạo source tên chung như `custom` hoặc `config` nếu chúng cần tồn tại đồng thời.
2. **Đặt cấu hình dùng chung ở parent.** Chỉ đưa cấu hình riêng của service vào child.
3. **Đừng dựa vào thứ tự ngầm.** Kiểm tra danh sách source và ghi rõ precedence khi nhiều nơi cùng khai báo một khóa.
4. **Thiết lập profile trước khi refresh context.** Bean `@Profile` được chọn trong quá trình đăng ký bean; đổi profile sau đó không tự động tái tạo mọi bean.
5. **Quyết định rõ Environment riêng hay dùng chung.** Shared Environment tiện cho đồng bộ nhưng làm giảm tính cô lập; Environment riêng cho phép cấu hình khác nhau nhưng cần merge/propagate có chủ đích.
6. **Không dùng hierarchy chỉ để tránh truyền cấu hình.** Cân nhắc Config Data, Config Server hoặc configuration object nếu hierarchy làm lifecycle phức tạp.
7. **Phân biệt legacy bootstrap với Config Data import.** Tài liệu và ví dụ cấu hình phải khớp mode và release train đang chạy.
8. **Test source collision và profile inheritance.** Đây là các lỗi có thể không xuất hiện trong một context đơn lẻ nhưng gây sai cấu hình khi triển khai hierarchy.

## 13. Checklist hoàn thành

- [ ] Giải thích được parent–child ApplicationContext và bean visibility.
- [ ] Phân biệt ApplicationContext hierarchy với Environment hierarchy.
- [ ] Mô tả được cách merge property sources và active/default profiles.
- [ ] Biết child source có ưu tiên hơn source được kế thừa từ parent khi source name khác nhau.
- [ ] Biết source cùng tên ở child thay thế source parent cùng tên, không merge theo key.
- [ ] Phân biệt setActiveProfiles và addActiveProfile.
- [ ] Giải thích được profile inheritance không làm parent bean được đăng ký lại.
- [ ] Phân biệt profile-specific config loading với PropertySource inheritance.
- [ ] Biết khi nào SpringApplicationBuilder dùng Environment riêng và khi nào chia sẻ.
- [ ] Phân biệt legacy bootstrap context với Config Data import.
- [ ] Hiểu remote PropertySource override policy của Spring Cloud Config.
- [ ] Có test cho key precedence, source-name collision, profile merge và context lifecycle.
- [ ] Có quy ước đặt tên PropertySource và nơi lưu cấu hình chung/cục bộ.

**Tài liệu chính thức nên đối chiếu theo phiên bản dự án:**

- [Spring Framework – ConfigurableEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html): thao tác PropertySource, active/default profiles và `merge(parent)`.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, hierarchy, Environment changes và remote PropertySource.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, legacy bootstrap và cách lấy remote configuration.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): active/default profiles, include, profile groups và profile-specific documents.

API, cách bootstrap và precedence có thể khác theo phiên bản Spring Boot/Spring Cloud. Khi áp dụng vào dự án, hãy đối chiếu đúng release train và kiểm thử Environment của từng context trước khi kết luận.
