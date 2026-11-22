# Quan sát PropertySource và nguồn gốc giá trị mà không in bí mật trong Spring Boot

## Mục tiêu

Khi một ứng dụng Spring Boot nhận giá trị cấu hình không như mong đợi, cách chẩn đoán nhanh nhất thường là tìm hiểu **nguồn cấu hình nào đang được ưu tiên**, property có thực sự tồn tại hay không, và Binder/bean cấu hình đã sử dụng đường dẫn nào. Tuy nhiên, việc kiểm tra Environment cũng dễ gây rò rỉ thông tin: cùng một Environment có thể chứa mật khẩu cơ sở dữ liệu, API key, access token, connection URL có thông tin xác thực, secret của Kubernetes, hoặc chuỗi được nạp từ một nguồn bí mật.

Vì vậy không nên chẩn đoán bằng cách in tất cả key/value:

~~~java
// KHÔNG NÊN LÀM:
System.out.println(environment.getSystemEnvironment());
System.out.println(environment.getSystemProperties());
System.out.println(environment.getProperty("spring.datasource.password"));
~~~

Các lệnh trên có thể đưa bí mật vào stdout, log của container, hệ thống thu thập log, CI artifacts hoặc ticket hỗ trợ. Một khi log được sao chép và lưu giữ ở nhiều nơi, việc thu hồi bí mật có thể tốn kém và không chắc chắn.

Cách chẩn đoán phù hợp là **quan sát cấu trúc và metadata**, không hiển thị giá trị thô. Bài học tập trung vào:

1. Hiểu thứ tự ưu tiên của Spring **PropertySource** và cách giải quyết property cuối cùng.
2. Liệt kê tên/loại nguồn một cách có kiểm soát, không dump nội dung.
3. Xác định một key canonical có được nguồn nào cung cấp và nguồn nào có ưu tiên cao nhất.
4. Phân biệt **PropertySource**, **ConfigurationPropertySource** của Binder và **Origin**.
5. Quan sát origin như file, resource hoặc vị trí dòng khi metadata có sẵn, đồng thời không giả định origin luôn tồn tại.
6. Dùng **/actuator/env** và **/actuator/configprops** một cách an toàn; giữ giá trị được che và giới hạn quyền truy cập.
7. Tránh rò rỉ qua debug logs, exceptions, shell commands, test output và báo cáo sự cố.
8. Chẩn đoán biến môi trường, JVM system property, CLI, Config Data imports, profile và relaxed binding.
9. Viết helper/test chẩn đoán trả về trạng thái có/không và loại nguồn, không trả raw value.
10. Xây quy trình runbook có thể áp dụng ở môi trường production mà không cần tiết lộ secret.

Các ví dụ ưu tiên API Spring Boot 3.x và Java 17+; hướng dẫn về các endpoint quản trị được nêu theo những đặc tính tương ứng trong tài liệu Spring Boot chính thức. Một số package và tùy chọn quản lý endpoint có thể thay đổi giữa Boot 3.x và Boot 4.x, nên cần đối chiếu phiên bản dự án khi triển khai.

---

## 1. Vấn đề điển hình: một giá trị được đặt ở nhiều nơi

Giả sử một HTTP client có timeout:

~~~yaml
# application.yml
app:
  gateway:
    timeout: 5s
~~~

Nhưng triển khai có profile production:

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 8s
~~~

Một biến môi trường còn được cấp:

~~~text
APP_GATEWAY_TIMEOUT=12s
~~~

Và khi khởi động tiến trình có CLI argument:

~~~text
--app.gateway.timeout=15s
~~~

Khi code đọc cấu hình, giá trị cuối có thể là **15 giây**, vì command-line argument có thứ tự ưu tiên cao hơn những nguồn kia trong trường hợp thông thường.

Để chẩn đoán, ta cần biết:

- Property nào đang được xét?
- Những nguồn nào có chứa property đó?
- Nguồn nào đứng trước trong thứ tự tra cứu?
- Có nguồn test, custom PropertySource hoặc extension nào chen vào không?
- Giá trị này sau binding có phải cùng kiểu với bean mong đợi không?

**Không cần in các giá trị 5s, 8s, 12s hay 15s để trả lời câu hỏi đầu tiên về nguồn nào thắng**, nếu một helper có thể báo rằng property được thấy trước tiên trong loại nguồn “command-line”.

Trong môi trường thực tế, app.gateway.timeout có thể là app.gateway.api-key. Khi đó cách chẩn đoán dựa vào cấu trúc thay vì giá trị trở thành yêu cầu bảo mật.

## 2. Phân biệt PropertySource, Environment và Binder

Ba lớp khái niệm:

**PropertySource** đại diện một nguồn property như systemEnvironment, systemProperties, commandLineArgs hoặc tài liệu Config Data.

**ConfigurableEnvironment** duy trì tập các PropertySource có thứ tự, cung cấp API tra cứu property và hỗ trợ chuyển kiểu cho những trường hợp thích hợp.

**Spring Boot Binder** liên kết các property theo dạng canonical và các quy tắc relaxed binding vào JavaBean, record, List, Map và nested object.

Sơ đồ:

~~~text
application.yml     application-prod.yml     env / JVM / CLI
       |                    |                      |
       +--------------------+----------------------+
                            |
                            v
                  MutablePropertySources
                  (danh sách có thứ tự)
                            |
             +--------------+--------------+
             |                             |
             v                             v
       Environment API                Binder API
       getProperty(...)               ConfigurationPropertySource
             |                             |
             v                             v
       giá trị hoặc null            @ConfigurationProperties
                                     Java object
~~~

### 2.1. Hai lời gọi khác nhau

~~~java
environment.getProperty("app.gateway.timeout");
~~~

và:

~~~java
Binder.get(environment)
      .bind("app.gateway.timeout", Duration.class);
~~~

đều có thể đọc cùng một khái niệm timeout, nhưng đi qua những cơ chế tra cứu/chuyển kiểu không hoàn toàn giống nhau.

Đặc biệt, Binder có các quy tắc canonical naming, relaxed binding, collection indices và map key. Một tìm kiếm exact key trên PropertySource không phải lúc nào cũng tương đương với việc Binder đã tìm thấy field Java.

### 2.2. Vì sao phải biết sự khác biệt?

Nếu thấy:

~~~text
APP_GATEWAY_READTIMEOUT
~~~

trong OS environment, nhưng gọi:

~~~java
source.containsProperty("app.gateway.read-timeout")
~~~

trên một PropertySource đơn lẻ, kết quả không nhất thiết thể hiện đầy đủ khả năng alias/canonicalization của Binder. Muốn phân tích đúng binding, nên dùng API ConfigurationPropertySource hoặc một Binder test phù hợp, không chỉ tìm chuỗi exact key.

---

## 3. Thứ tự PropertySource có ý nghĩa gì?

Trong **ConfigurableEnvironment**, danh sách PropertySource có thứ tự. Khi một property được yêu cầu, những nguồn được ưu tiên cao hơn thường được xét trước những nguồn thấp hơn.

Các nguồn phổ biến gồm:

- Command-line arguments.
- JVM system properties.
- OS environment variables.
- Config Data như application.properties/application.yml.
- File theo profile và file import.
- Các nguồn do SpringApplication hoặc thư viện bổ sung.
- Những nguồn cấu hình được thêm trong test.

Lưu ý: đây không phải bảng cam kết một thứ tự tuyệt đối cho mọi ứng dụng; test properties, DynamicPropertySource, devtools, JNDI, servlet parameters, custom PropertySource và các extension có thể làm thứ tự thực tế khác.

**Muốn biết thứ tự thực của một tiến trình, quan sát danh sách PropertySource đã có trong Environment của chính tiến trình đó.**

### 3.1. Thứ tự trong danh sách không đồng nghĩa vị trí thời gian

Một EnvironmentPostProcessor có thể chạy sau khi Config Data được nạp nhưng gọi **addFirst**, đặt source của nó trên cả nguồn có sẵn.

Vì vậy “source được tạo cuối cùng” không mặc nhiên có ưu tiên thấp nhất hay cao nhất. Điều quan trọng là vị trí trong danh sách sau cùng.

### 3.2. Một key có thể xuất hiện nhiều lần

Ví dụ:

~~~text
app.gateway.timeout
  -> commandLineArgs
  -> systemEnvironment
  -> Config resource application-prod.yml
  -> Config resource application.yml
~~~

Các nguồn thấp hơn không bị xóa; chúng vẫn tồn tại nhưng bị che bởi nguồn đứng trước đối với key trùng nhau.

Việc một cấu hình có trong YAML không chứng minh YAML là nguồn thắng. Cần xét toàn bộ thứ tự và các cơ chế chuyển tên có liên quan.

---

## 4. Nguyên tắc bảo mật: xem metadata trước, giá trị sau

Khi production có lỗi cấu hình, đừng mở đầu bằng câu hỏi “giá trị thật là gì?”. Hãy hỏi:

1. Key có được yêu cầu đúng tên không?
2. Nguồn nào chứa key?
3. Nguồn nào đang thắng?
4. Origin metadata có hỗ trợ xác định file/line không?
5. Có bất kỳ source nào mới được thêm bởi runtime, test hoặc library không?
6. Bean có bị lỗi conversion/validation không?
7. Có cần tiếp cận giá trị thật để giải quyết vấn đề không?

Trong nhiều sự cố, chỉ cần 1–6.

### 4.1. Phân cấp mức độ dữ liệu được phép quan sát

| Thông tin | Mức rủi ro | Hướng xử lý |
| --- | --- | --- |
| Tên nhóm cấu hình đã được cho phép | Thấp hơn | Chỉ hiển thị theo allowlist |
| PropertySource category | Thấp hơn | Có thể ghi log có kiểm soát |
| Vị trí ưu tiên của source | Thấp hơn | Hữu ích khi chẩn đoán |
| Có/không có origin metadata | Thấp hơn | Có thể ghi trạng thái boolean |
| Đường dẫn file resource đầy đủ | Có thể nhạy cảm | Chỉ xem trong tooling kiểm soát; cân nhắc rút gọn |
| Tên env var chứa tenant/customer ID | Có thể nhạy cảm | Không quét và xuất hàng loạt |
| Raw property value | Có thể là secret | Không log / chỉ xem qua quy trình được cấp quyền |
| Credential, password, token, private key | Rất cao | Không hiển thị trong diagnostic thông thường |

Ngay cả **metadata** cũng có thể tiết lộ cấu trúc hạ tầng, tên tenant, địa chỉ nội bộ hoặc đường dẫn chứa username. Vì vậy “không in value” là điều kiện cần nhưng chưa luôn đủ.

---

## 5. Liệt kê PropertySource mà không in value

Một ví dụ trong mã Java:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceInspector {

    public static void printSourceTypes(
            ConfigurableEnvironment environment) {

        int order = 0;
        for (PropertySource<?> source
                : environment.getPropertySources()) {

            order++;

            System.out.printf(
                "position=%d type=%s%n",
                order,
                source.getClass().getSimpleName()
            );
        }
    }
}
~~~

Đoạn này chỉ in **vị trí** và **tên loại class**. Nó không gọi:

~~~java
source.getProperty(key)
source.getSource()
source.toString()
~~~

nên tránh nhiều cách vô tình in nguyên nội dung source.

### 5.1. Có nên in source.getName()?

**PropertySource.getName()** thường hữu ích vì có thể cho biết tên như commandLineArgs, systemEnvironment hoặc tên một tài liệu cấu hình.

Nhưng với nguồn file, tên có thể chứa đường dẫn, resource URI hoặc dữ liệu tổ chức nhạy cảm. Vì thế ở production, có thể chỉ ghi loại source, hoặc ánh xạ các tên đã biết sang nhãn an toàn.

Ví dụ:

~~~java
private static String safeSourceLabel(String name) {
    return switch (name) {
        case "commandLineArgs" -> "CLI";
        case "systemEnvironment" -> "OS_ENV";
        case "systemProperties" -> "JVM_SYSTEM";
        default -> "OTHER_SOURCE";
    };
}
~~~

Đây là bộ nhãn minh họa; trong ứng dụng thật, source names có thể khác, cần test với Environment mục tiêu.

**Không tự đưa raw source.getName() vào nhãn mặc định** nếu source name có thể chứa file path hoặc URI.

### 5.2. Không dump source.getSource()

Một số PropertySource chứa Map hoặc object đại diện cho nguồn thực. Lời gọi:

~~~java
System.out.println(source.getSource());
~~~

có thể in toàn bộ key/value, gồm cả bí mật. Đây là một antipattern cần tránh ngay cả trong log level DEBUG.

---

## 6. Xác định nguồn thắng mà không in giá trị

Nếu chỉ muốn xem một key có mặt trong source nào, có thể viết helper trả về **vị trí ưu tiên** mà không trả raw value.

Tuy nhiên, API **PropertySource.containsProperty(...)** sử dụng tên key theo cách của PropertySource cụ thể và có thể không tái hiện toàn bộ relaxed binding.

Ví dụ cơ bản:

~~~java
public static int firstExactSourceIndex(
        ConfigurableEnvironment environment,
        String exactName) {

    int index = 0;
    for (PropertySource<?> source :
            environment.getPropertySources()) {

        index++;
        if (source.containsProperty(exactName)) {
            return index;
        }
    }

    return -1;
}
~~~

Kết quả **1** nghĩa là key exact có trong source đầu tiên được xét; **-1** nghĩa không tìm thấy theo phép kiểm tra exact này.

### 6.1. Hạn chế của cách exact-key

Không nên dùng kết quả **-1** để khẳng định một @ConfigurationProperties field chắc chắn không bind được. Một env var dạng upper underscore có thể được Spring Boot Binder ánh xạ từ canonical key theo cơ chế riêng.

Nếu mục tiêu là **nguồn nào bind canonical property**, dùng ConfigurationPropertySources như phần tiếp theo.

### 6.2. Không quét mọi property name

Để quan sát một key được phép, **chỉ kiểm tra key đó**. Không duyệt toàn bộ keys của systemEnvironment, systemProperties hoặc các enumerable sources rồi in ra log.

Dù không in values, một danh sách tên biến cũng có thể tiết lộ provider, khách hàng, secret names, dịch vụ nội bộ hoặc cấu trúc triển khai.

---

## 7. ConfigurationPropertySource: góc nhìn gần Binder hơn

Spring Boot cung cấp:

~~~java
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.boot.context.properties.source.ConfigurationProperty;
~~~

**ConfigurationPropertySources.from(...)** có thể tạo những adapter từ các Spring PropertySource hiện có, giúp kiểm tra key theo dạng ConfigurationPropertyName.

Ví dụ chỉ quan sát sự hiện diện:

~~~java
import org.springframework.boot.context.properties.source.ConfigurationProperty;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.ConfigurableEnvironment;

public final class CanonicalPropertyProbe {

    public static int firstMatchingSource(
            ConfigurableEnvironment environment,
            String canonicalProperty) {

        ConfigurationPropertyName name =
                ConfigurationPropertyName.of(canonicalProperty);

        int position = 0;

        for (ConfigurationPropertySource source :
                ConfigurationPropertySources.from(
                    environment.getPropertySources())) {

            position++;

            ConfigurationProperty property = source.get(name);

            if (property != null) {
                // Chỉ trả vị trí nguồn; tuyệt đối không in property.
                return position;
            }
        }

        return -1;
    }
}
~~~

Ví dụ lời gọi:

~~~java
int position = CanonicalPropertyProbe.firstMatchingSource(
        environment,
        "app.gateway.read-timeout"
);

System.out.println("source-position=" + position);
~~~

Điều được in là **một số nguyên**, không phải property value.

### 7.1. Vì sao dùng from(...) thay vì get(environment)?

**ConfigurationPropertySources.get(environment)** trả về các nguồn đã được **attach** vào Environment. Nó có thể báo lỗi nếu môi trường chưa được gắn support tương ứng.

**ConfigurationPropertySources.from(environment.getPropertySources())** tạo adapter từ danh sách hiện tại, phù hợp cho một helper chỉ đọc đang có ConfigurableEnvironment. Với một ứng dụng Spring Boot chuẩn, Binder còn có những đường tích hợp khác phù hợp vòng đời context.

### 7.2. Tên canonical cần được tạo đúng

Ví dụ canonical:

~~~text
app.gateway.read-timeout
spring.datasource.hikari.maximum-pool-size
app.clients[0].name
~~~

Không truyền bừa tên env upper underscore vào ConfigurationPropertyName.of(...) rồi mong nó xử lý như một canonical path. Cần chọn đúng **đường dẫn logical property** của bean.

### 7.3. Đọc ConfigurationProperty cũng đọc object value trong bộ nhớ

Lời gọi **source.get(name)** trả về ConfigurationProperty, trong đó có thể chứa value. Ví dụ trên **không in hoặc lưu** value, chỉ kiểm tra object khác null.

Nếu trong tổ chức có policy cấm cả việc truy cập secret ở một module không có quyền, hãy áp dụng allowlist và quyền gọi helper. Không nên cung cấp endpoint mở cho người dùng truyền bất kỳ key nào để thực hiện lookup.

---

## 8. Quan sát origin của cấu hình

**Origin** là metadata mô tả nguồn gốc của một property: có thể là một resource, dòng/cột của file, nguồn môi trường hoặc thông tin đặc thù mà PropertySource cung cấp.

Trong Spring Boot, các API liên quan gồm:

~~~java
org.springframework.boot.origin.Origin
org.springframework.boot.origin.OriginLookup
org.springframework.boot.context.properties.source.ConfigurationProperty
~~~

Với một ConfigurationProperty:

~~~java
Origin origin = property.getOrigin();
~~~

Origin có thể null khi nguồn không hỗ trợ theo dõi origin.

### 8.1. Không nhầm origin với value

Ví dụ mô tả:

~~~text
logical property: app.gateway.timeout
source category:  CONFIG_DATA
origin available: true
value:            [KHÔNG HIỂN THỊ]
~~~

Origin có thể cho biết file và dòng của giá trị, nhưng thông tin file/line không phải bản thân value.

### 8.2. Origin metadata không luôn có

Một file YAML/properties được Spring Boot Config Data loader nạp thường có cơ chế origin tracking.

Một MapPropertySource do code tự tạo từ Map.of có thể không cung cấp origin chi tiết.

Một source tùy chỉnh của thư viện có thể chỉ có tên source, không có file hay line number.

**Nếu property.getOrigin() là null, báo “origin unavailable”, không tự dựng một đường dẫn giả.**

### 8.3. Cảnh báo về origin.toString()

Một đoạn code:

~~~java
System.out.println(property.getOrigin());
~~~

có thể in ra đường dẫn resource hoặc thông tin cấu trúc triển khai. Nó không nhất thiết in secret value, nhưng vẫn có thể tiết lộ folder/username hoặc URI chứa phần nhạy cảm.

Trong production, hãy ưu tiên **originAvailable=true/false** hoặc một nhãn đã được chuẩn hóa. Chỉ xem origin chi tiết trong công cụ chẩn đoán đã xác thực, có audit, và phải có quy tắc redaction đối với path/URI.

---

## 9. Helper an toàn: chỉ ghi nguồn loại nào và có origin không

Một helper không trả property value:

~~~java
package example.diagnostics;

import org.springframework.boot.context.properties.source.ConfigurationProperty;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.ConfigurableEnvironment;

public final class SafeConfigProbe {

    public record SourceFinding(
            boolean found,
            int sourcePosition,
            String sourceType,
            boolean originAvailable
    ) {}

    public static SourceFinding inspect(
            ConfigurableEnvironment environment,
            String canonicalName) {

        ConfigurationPropertyName name =
                ConfigurationPropertyName.of(canonicalName);

        int position = 0;

        for (ConfigurationPropertySource source :
                ConfigurationPropertySources.from(
                    environment.getPropertySources())) {

            position++;

            ConfigurationProperty property = source.get(name);

            if (property != null) {
                // Không gọi property.getValue(), property.toString()
                // hoặc property.getOrigin().toString().
                return new SourceFinding(
                    true,
                    position,
                    source.getClass().getSimpleName(),
                    property.getOrigin() != null
                );
            }
        }

        return new SourceFinding(
            false,
            -1,
            "NONE",
            false
        );
    }

    private SafeConfigProbe() {}
}
~~~

Cách sử dụng với **key allowlist**:

~~~java
var finding = SafeConfigProbe.inspect(
        environment,
        "app.gateway.timeout"
);

logger.info(
        "gateway timeout config: found={}, sourcePosition={}, " +
        "originAvailable={}",
        finding.found(),
        finding.sourcePosition(),
        finding.originAvailable()
);
~~~

**Không đưa canonicalName nhận từ request không kiểm soát vào logger hoặc cho phép truy vấn arbitrary key.** Với API production, hãy tạo một registry những property **không nhạy cảm** được phép kiểm tra.

### 9.1. Vì sao không log SourceFinding toàn bộ?

Record trong ví dụ chỉ chứa boolean, số và tên kiểu class, nên an toàn hơn record chứa giá trị. Dù vậy, nguyên tắc tốt là log **những field thật sự cần**, không dùng toString của mọi diagnostic object như một thói quen.

### 9.2. Vị trí source không phải một mã định danh bền

Source position = 3 ở hôm nay có thể thành 4 sau khi một thư viện thêm PropertySource. Nó hữu ích trong một lần quan sát, nhưng không phải business identifier nên lưu cố định.

Nếu cần một category ổn định, hãy chuyển source names thành nhãn nội bộ an toàn thông qua danh sách được kiểm soát.

### 9.3. Không hứa đây là một “Binder trace” hoàn chỉnh

Một Binder bind List, Map, placeholders, aliases hoặc nested object có thể tra cứu nhiều property và thực hiện conversion. Helper này chỉ kiểm tra **một canonical property** theo thứ tự những nguồn đã adapt.

Nó là công cụ định hướng, không phải bản ghi mọi bước nội bộ Binder hay tất cả các thuộc tính cấu thành object cuối.

---

## 10. OriginLookup với PropertySource gốc

Ngoài ConfigurationProperty.getOrigin(), Spring Boot cung cấp **OriginLookup**. Một số PropertySource có khả năng cho biết origin từ key.

Ý tưởng:

~~~java
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;
import org.springframework.core.env.PropertySource;

Origin origin =
        OriginLookup.getOrigin(source, "app.gateway.timeout");
~~~

Với một source hỗ trợ OriginLookup, kết quả có thể là một Origin. Nếu không hỗ trợ, có thể trả null.

### 10.1. Cảnh báo về key và relaxed binding

**OriginLookup trên một PropertySource gốc** có thể yêu cầu key đúng theo cách source đó lưu trữ. Đây không phải bảo đảm tự tìm origin từ mọi alias của Binder.

Nếu đang phân tích @ConfigurationProperties, cách dùng **ConfigurationPropertySources.from(...)** và **ConfigurationProperty.getOrigin()** thường gần với canonical binding hơn.

### 10.2. Origin không nhất thiết chỉ là file:line

Nguồn có thể là:

- Config Data từ resource trong classpath.
- File ngoài JAR.
- Environment variable.
- Configuration tree.
- Source do thư viện cung cấp.
- Một nguồn không biết origin.

Vì thế đừng thiết kế API diagnostic chỉ có **path** và **line** bắt buộc. Nên dùng **originAvailable** và một kiểu metadata có thể vắng mặt.

### 10.3. Không tự copy origin metadata sang log

Kể cả chỉ là file path, một origin có thể chứa tên người dùng, tenant, cấu trúc thư mục, URL hoặc dữ liệu bị đưa nhầm vào source name.

Nếu có nhu cầu lưu origin để điều tra, hãy giới hạn phạm vi lưu trữ và áp dụng sanitizer dựa trên **allowlist dạng resource an toàn**, không dựa vào một regex che những từ password/token.

---

## 11. Actuator: env và configprops dùng để làm gì?

Khi có Spring Boot Actuator phù hợp, hai endpoint hữu ích:

- **/actuator/env**: quan sát thông tin về các PropertySource và các thuộc tính trong ConfigurableEnvironment.
- **/actuator/configprops**: quan sát danh sách các bean @ConfigurationProperties và thông tin cấu hình được bind, trong phạm vi những dữ liệu endpoint cung cấp.

Tài liệu Spring Boot xem đây là các công cụ giúp tìm hiểu vì sao một property có giá trị cụ thể.

### 11.1. Giá trị được che theo mặc định

Trong các dòng Spring Boot hiện hành, các endpoint **env**, **configprops** và một số endpoint khác có cơ chế **sanitization**. Theo mặc định, values có thể được thay bằng dạng che như:

~~~text
******
~~~

Đây là đặc tính quan trọng, nhưng không nên hiểu rằng endpoint có thể được công khai cho mọi người: tên property, danh sách nguồn và metadata vẫn có thể tiết lộ thông tin hạ tầng.

### 11.2. Không tự đặt show-values=always để debug

Cấu hình nguy hiểm trong nhiều hoàn cảnh:

~~~properties
management.endpoint.env.show-values=always
management.endpoint.configprops.show-values=always
~~~

Tùy phiên bản và SanitizingFunction, điều này có thể cho phép hiển thị nhiều giá trị ở dạng không bị che cho người có khả năng truy cập endpoint.

**Không nên dùng trong production** chỉ để giải một sự cố timeout hoặc profile. Rủi ro lộ password và token không tương xứng với lợi ích.

### 11.3. Cách giữ values được che

Ví dụ cấu hình chủ động:

~~~properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

Đây là cấu hình thiên về an toàn: quan sát metadata nhưng không cho xem raw values qua hai endpoint.

**Lưu ý:** cú pháp quyền truy cập/endpoint availability có thay đổi theo phiên bản Boot; hãy xác nhận setting của ứng dụng. Ngay cả khi show-values=never, phải tiếp tục giới hạn access/exposure của env và configprops.

### 11.4. when-authorized vẫn cần cân nhắc nghiêm túc

Spring Boot hỗ trợ chế độ **when-authorized** cho một số endpoint. Chế độ đó có thể hiển thị giá trị thật cho người dùng được coi là authorized theo cấu hình security/roles.

Ví dụ minh họa cho env:

~~~properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=admin
~~~

**Đây không phải cấu hình mặc định được khuyến nghị cho chẩn đoán không lộ bí mật.** Khi đã authorized, nhiều giá trị có thể trở nên hiển thị; hãy đánh giá chính sách dữ liệu và mức độ tin cậy của role đó.

Nếu mục tiêu chỉ xác định “source nào đang thắng”, giữ **never** sẽ đáp ứng an toàn hơn.

---

## 12. Đừng công khai /actuator/env hoặc /actuator/configprops

Trong nhiều cấu hình Spring Boot, chỉ health được expose qua HTTP mặc định; các endpoint nhạy cảm cần được bật thêm theo chính sách quản trị.

Không nên triển khai:

~~~properties
management.endpoints.web.exposure.include=*
~~~

rồi nghĩ rằng giá trị có masking nên không còn vấn đề. Endpoint khác có thể tiết lộ thông tin về bean, mappings, logs hoặc environment.

Nếu thực sự cần dùng env/configprops trong một môi trường chẩn đoán:

- Ưu tiên cổng management riêng, private network và firewall.
- Cấu hình Spring Security/authorization phù hợp.
- Chỉ expose endpoint cần thiết trong thời gian cần thiết.
- Giữ show-values=never.
- Có access log và audit cho truy vấn diagnostic.
- Không dùng token quản trị trong script hoặc ticket được chia sẻ.
- Gỡ exposure sau khi hoàn tất nếu nó chỉ được bật tạm thời.
- Rà soát rủi ro metadata, không chỉ values.

### 12.1. Mẫu phạm vi hẹp

Nếu môi trường đã có lớp bảo vệ quản trị thực sự và chính sách cho phép:

~~~properties
management.endpoints.web.exposure.include=health,info,env,configprops
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

Đây chỉ là ví dụ **liệt kê endpoint sẽ expose**, không bao gồm cấu hình firewall/authentication. **Không được sao chép nguyên vào production công khai** khi chưa có cơ chế kiểm soát truy cập.

### 12.2. JMX cũng là bề mặt truy cập

Không nên chỉ tập trung HTTP. Các endpoint quản trị có thể tồn tại qua JMX tùy cấu hình, và chính sách show-values/authorization có khác biệt với HTTP.

Nếu hệ thống không cần JMX management, kiểm tra exposure tương ứng. Không mở JMX từ xa mà không có authentication, network isolation và logging phù hợp.

---

## 13. Quan sát một property thay vì xuất toàn bộ Environment

Khi cần truy tìm một key cụ thể, truy vấn có phạm vi hẹp thường có lợi hơn liệt kê mọi property.

Ví dụ URL endpoint theo mặc định:

~~~text
/actuator/env/app.gateway.timeout
~~~

Endpoint có thể cung cấp thông tin về property và các nguồn có liên quan, theo định dạng cụ thể của phiên bản Boot, với values chịu sanitization.

Trước khi sử dụng, cần xác nhận:

- Endpoint đã được expose và bảo vệ.
- show-values giữ ở **never**.
- Tên property đã được chọn là an toàn để đưa vào URL/log truy cập.
- Query không chứa secret value hay token.
- Những metadata như source name và origin có được phép người xem biết không.

### 13.1. URL truy vấn cũng có thể bị ghi log

Nếu một người đưa secret vào path/query parameter, web server/proxy có thể ghi lại URL. Đừng dùng một endpoint query như cách truyền trực tiếp password/token.

Chỉ truyền tên key trong allowlist, không truyền giá trị.

### 13.2. Cẩn thận khi copy JSON vào ticket

Ngay cả khi values được che, response có thể chứa tên key, tên resource, profile hoặc đường dẫn file. Trước khi copy vào hệ thống ticket, hãy lọc về đúng các trường cần thiết, bỏ metadata ngoài phạm vi điều tra.

Không paste toàn bộ /actuator/env JSON vào một chat công khai hoặc một repository issue chỉ vì values hiện là ******.

---

## 14. /actuator/configprops và giới hạn của nó

/actuator/configprops giúp quan sát cấu hình đã được liên kết với các bean @ConfigurationProperties.

Ví dụ record:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        Duration timeout,
        String apiKey
) {}
~~~

Endpoint có thể hỗ trợ chẩn đoán bean và những đầu vào liên quan, nhưng phải tính đến sanitization và format tùy phiên bản.

### 14.1. Không đồng nhất Environment với object đã bind

Một property có thể tồn tại trong Environment nhưng:

- Bean @ConfigurationProperties chưa được đăng ký.
- Prefix của bean không khớp.
- Kiểu dữ liệu không chuyển đổi được.
- Một nested object không được tạo.
- Validation từ chối object.
- Bean được tạo trước khi nguồn mới được thêm.
- Một @ConditionalOnProperty khiến bean không tồn tại.

Vì vậy /actuator/env trả lời câu hỏi về Environment; /actuator/configprops hỗ trợ nhìn vào **binding đối với những bean cấu hình**.

### 14.2. Không in record.toString()

Record tự sinh toString chứa các component values. Một record có apiKey hoặc password có thể in nguyên thông tin:

~~~java
// TRÁNH:
log.info("GatewayProperties={}", gatewayProperties);
~~~

Nếu chỉ cần xác nhận bean tồn tại:

~~~java
log.info("GatewayProperties loaded");
~~~

Nếu muốn biết thuộc tính có mặt hay không, hãy tạo một boolean trạng thái không tiết lộ nội dung, và chỉ ghi khi đó là thông tin được phép quan sát.

### 14.3. Masking ở Actuator không bảo vệ mọi nơi

Ngay cả khi Actuator show-values=never, debug code tự in gatewayProperties, exception custom hoặc tracing interceptor vẫn có thể lộ secret.

Cần coi việc bảo vệ log và API quản trị là **hai lớp kiểm soát độc lập**.

---

## 15. Origin metadata từ YAML/properties

Với file:

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 12s
~~~

Spring Boot có thể giữ metadata nguồn gốc của property, chẳng hạn resource và vị trí văn bản.

Một ví dụ thông tin khái niệm:

~~~text
property: app.gateway.timeout
source: config data resource
origin: resource location / line information
value: hidden
~~~

**Không phải mọi PropertySource đều có origin tương đương.** File đọc bằng Spring Boot Config Data loader có khả năng tracking khác với MapPropertySource được tạo thủ công.

### 15.1. Khi file import ghi đè file gốc

application.yml:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway-extra.yml"
~~~

Nếu import cung cấp một key trùng, source thắng có thể đến từ file import. Origin giúp xác định resource thực tế, nhưng phải đồng thời xem **precedence**.

Một file có origin đúng không có nghĩa nó là nguồn thắng, nếu còn CLI/system property cao hơn.

### 15.2. File name có thể là dữ liệu nhạy cảm

Một path như:

~~~text
/home/<user>/secrets/customer-alpha/application.yml
~~~

tiết lộ cấu trúc filesystem hoặc tenant. Trong production logs, nên chuẩn hóa thành nhãn như **CONFIG_DATA_EXTERNAL** thay vì in nguyên path.

---

## 16. Biến môi trường: tên có thể đúng nhưng key exact không thấy

Canonical property:

~~~text
app.gateway.read-timeout
~~~

Tên env chuẩn:

~~~text
APP_GATEWAY_READTIMEOUT
~~~

Quy tắc Spring Boot áp dụng khi chuyển canonical key sang tên env:

1. Thay dấu chấm bằng underscore.
2. Bỏ dấu gạch ngang.
3. Chuyển chữ hoa.

Một sai sót hay gặp là đặt:

~~~text
APP_GATEWAY_READ_TIMEOUT
~~~

rồi chờ Binder hiểu giống **app.gateway.read-timeout** trong mọi trường hợp. Cách đặt tên này không phải chuyển đổi chuẩn của canonical key ở trên.

### 16.1. Không dump System.getenv()

Lệnh:

~~~java
System.getenv().forEach(
        (key, value) -> log.info("{}={}", key, value)
);
~~~

có thể lộ toàn bộ secret được inject vào container.

Ngay cả:

~~~bash
printenv
~~~

hoặc:

~~~bash
env
~~~

khi chạy trong debug session có output được lưu vào transcript cũng có nguy cơ lộ bí mật.

Thay vào đó, hãy xác minh **tên biến đã biết** có tồn tại hay không tại một điểm được kiểm soát, không in value:

~~~java
boolean present =
        System.getenv().containsKey("APP_GATEWAY_READTIMEOUT");
~~~

### 16.2. Không tự suy ra Environment chỉ vì System.getenv có biến

Binder có thể đọc nguồn khác ưu tiên cao hơn env, hoặc nguồn environment đang được adapt theo quy tắc riêng. Một env var có mặt không chứng minh nó là giá trị cuối.

Cần kiểm tra thứ tự các PropertySource và key canonical trong Environment.

### 16.3. Quản lý tên biến secret

Ngay cả tên biến như **TENANT_X_SECRET_KEY** có thể tiết lộ tên tenant hoặc loại credential. Vì vậy không xuất danh sách tất cả env keys.

---

## 17. JVM properties và command-line arguments

Một ứng dụng có thể chạy với:

~~~bash
java -Dapp.gateway.timeout=9s -jar demo.jar \
  --app.gateway.timeout=11s
~~~

JVM property thường nằm trong systemProperties, CLI trong commandLineArgs.

Nếu chẩn đoán thấy nguồn command-line thắng, không cần in toàn bộ arguments.

### 17.1. Vì sao không in argv?

Các tham số dòng lệnh có thể chứa:

~~~text
--app.external.api-key=...
--spring.datasource.password=...
~~~

In nguyên **ApplicationArguments** hoặc danh sách đối số có thể làm lộ token.

Ngay cả command line có thể bị quan sát bởi công cụ quản lý tiến trình tùy hệ điều hành. Tốt nhất là **không truyền secret thô qua CLI** khi nền tảng có cách an toàn hơn.

### 17.2. Chỉ log nguồn của key cho phép

Ví dụ:

~~~text
app.gateway.timeout: winner=CLI
~~~

có ích khi chẩn đoán timeout. Không cần:

~~~text
app.gateway.timeout: value=11s
~~~

Với secret, thậm chí tên key cũng có thể cần được ẩn hoặc ánh xạ sang mã định danh không tiết lộ.

---

## 18. PropertySource priority và binder precedence

Một số vấn đề xuất hiện khi người vận hành nhìn thấy hai giá trị trong hai file nhưng không hiểu tại sao một giá trị được chọn.

Ví dụ:

~~~yaml
# application.yml
app:
  gateway:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 10s
~~~

Khi profile prod hoạt động, config data theo profile có thể ghi đè file nền.

Nếu còn env var, system property hoặc CLI, nguồn đó có thể ghi đè tiếp tùy thứ tự.

### 18.1. Không cần log raw values

Một báo cáo an toàn:

~~~text
propertyGroup=GATEWAY_TIMEOUT
profileActivated=true
winningSourceCategory=CLI
originAvailable=false
valuePrinted=false
~~~

Báo cáo này giúp khoanh vùng rằng câu hỏi phải chuyển từ file profile sang tham số khởi động, mà không chứa giá trị.

### 18.2. Origin ở file nền không chứng minh file nền được dùng

Một key có thể tồn tại trong application.yml nhưng bị ghi đè bởi application-prod.yml. Nếu chỉ đọc origin của file nền đã biết, bạn chưa biết giá trị cuối.

Phải xác định **nguồn thắng trước**, sau đó mới quan sát origin của đúng nguồn đó.

---

## 19. List và Map: chẩn đoán cấu trúc, không chỉ một key

Đối với List:

~~~yaml
app:
  clients:
    - name: primary
      timeout: 3s
    - name: backup
      timeout: 5s
~~~

Các property logic:

~~~text
app.clients[0].name
app.clients[0].timeout
app.clients[1].name
app.clients[1].timeout
~~~

Nếu một profile khác ghi List chỉ có phần tử index 0, Spring Boot thường dùng List của nguồn có ưu tiên cao hơn thay vì tự ghép phần tử hai nguồn.

### 19.1. Đừng chỉ xem app.clients[0].name

Một List có thể có các phần tử thiếu field hoặc số lượng thay đổi. Để chẩn đoán cần biết:

- List cuối có bao nhiêu phần tử?
- Nguồn nào đang cung cấp các index?
- Có một List từ profile cao hơn thay thế List nền không?
- Constraint của từng element có báo lỗi không?

Không cần in tên server hoặc endpoint thật trong log để biết số lượng phần tử hay tình trạng validation.

### 19.2. Map có hành vi kết hợp key khác List

Với Map:

~~~yaml
app:
  labels:
    owner: platform
    region: global
~~~

và một nguồn ưu tiên cao hơn khai báo region khác, Map có thể kết hợp các key, còn key trùng chọn theo precedence.

Để chẩn đoán một Map, hãy kiểm tra cấu trúc và nguồn của **những key được phép**, tránh enumerate mọi key vì key có thể chứa customer ID hoặc secret names.

### 19.3. Mỗi phần tử có thể có origin khác nhau

Không nên báo:

~~~text
app.clients -> origin=application-prod.yml
~~~

rồi khẳng định toàn bộ object được tạo từ một file duy nhất trong mọi trường hợp. Với nested Map, placeholders hoặc nhiều source, các field có thể được giải quyết từ các nguồn khác nhau.

---

## 20. Placeholder và giá trị cuối

Một property có thể được định nghĩa bằng placeholder:

~~~properties
app.gateway.timeout=5s
app.gateway.endpoint=https://example.test
~~~

Hoặc một cấu hình ứng dụng có thể dùng tham chiếu đến property khác qua cơ chế placeholder của Spring.

Khi đó:

- Origin của key được khai báo có thể chỉ tới dòng chứa placeholder.
- Giá trị sau khi resolve có thể lấy dữ liệu từ một key khác và chịu precedence riêng.
- Một Binder object cuối cùng có thể chứa giá trị đã qua conversion.

**Đừng coi origin của một dòng là danh sách đầy đủ tất cả các nguồn ảnh hưởng đến giá trị cuối.**

### 20.1. Bí mật có thể nằm trong placeholder

Nếu endpoint được dựng từ username/password hoặc token, in URL cuối cùng có thể lộ credential ngay cả khi key tên endpoint không có chữ password.

Vì vậy quy tắc “chỉ che key chứa password/token” không đủ. Đừng in bất kỳ raw value nào trong một diagnostic mặc định.

### 20.2. Đừng tự gọi resolver để log value

Một helper chẩn đoán có thể vô tình gọi getProperty rồi đưa kết quả qua String.format. Tránh:

~~~java
log.debug(
    "resolved property={}",
    environment.getProperty(key)
);
~~~

Thay bằng trạng thái:

~~~java
boolean configured =
        environment.containsProperty(allowedKey);
log.debug("configured={}", configured);
~~~

Và ghi rõ rằng containsProperty chỉ giải quyết câu hỏi có mặt theo Environment API, không phải bằng chứng mọi constraint hoặc binding thành công.

---

## 21. Đọc lỗi binding mà không copy giá trị bị từ chối

Spring Boot có thể báo lỗi conversion hoặc Bean Validation khi dữ liệu không hợp lệ.

Ví dụ:

~~~properties
app.gateway.pool.max-connections=abc
~~~

trong khi Java cần int. Lỗi conversion có thể xảy ra trước validation.

Nếu value là một bí mật thay vì **abc**, một lỗi hoặc custom exception được cấu hình không cẩn thận có thể đưa rejected value vào output.

### 21.1. Không tự tạo exception chứa raw config

Tránh:

~~~java
throw new IllegalArgumentException(
        "Invalid property " + key + "=" + value
);
~~~

Một hướng an toàn hơn:

~~~java
throw new IllegalArgumentException(
        "Invalid configuration for gateway pool size"
);
~~~

Nếu cần thông tin kỹ thuật, ghi mã lỗi, đường dẫn property đã được allowlist và loại lỗi. Không đưa password/token vào message.

### 21.2. Root cause hữu ích hơn việc dump dữ liệu

Khi thấy failure, xác định nó thuộc nhóm:

- Source không có key.
- Property name sai.
- Profile/import không được nạp.
- Source precedence không như mong đợi.
- Conversion failure.
- Constructor binding failure.
- Validation failure.
- Bean registration/condition failure.

Có thể định danh nhóm lỗi mà không log raw values.

### 21.3. Validation không thay thế sanitization

Một @NotBlank trên password có thể kiểm tra password có tồn tại, nhưng điều đó không bảo đảm log exception sẽ che password. Sanitization là một trách nhiệm độc lập.

---

## 22. Vì sao logging ở mức TRACE/DEBUG có thể nguy hiểm?

Khi gặp lỗi khó, người vận hành dễ bật logging cực chi tiết cho Spring Boot Binder, Environment, Config Data hoặc HTTP client.

Một số logger có thể phát ra nhiều thông tin hơn dự đoán, đặc biệt nếu ứng dụng hoặc thư viện custom tự log Map/value.

Không nên:

~~~properties
logging.level.root=TRACE
~~~

trên toàn bộ production để tìm một property đơn lẻ.

### 22.1. Thay bằng chẩn đoán hẹp

Một lộ trình ít rủi ro hơn:

1. Xác định canonical key.
2. Dùng helper allowlist báo nguồn đầu tiên.
3. Kiểm tra active profiles và danh sách source type.
4. Kiểm tra conversion/validation bằng test cô lập.
5. Chỉ bật logging chuyên biệt trong môi trường được kiểm soát khi các bước trên chưa đủ.
6. Có thời hạn tắt debug và chính sách xóa log nếu phát sinh dữ liệu nhạy cảm.

### 22.2. Chế độ debug không tự đồng nghĩa an toàn

Bật debug của Spring Boot có thể giúp xem condition evaluation và một số thông tin khởi động. Nhưng đừng suy ra mọi thư viện và custom logger đều redacted secret.

Hãy kiểm tra chính những loggers được bật, mẫu thông điệp và appender trước khi áp dụng.

---

## 23. Log dữ liệu cấu hình bằng allowlist, không bằng blacklist

Một blacklist kiểu:

~~~text
Nếu key chứa password, token, secret thì che.
Ngược lại in bình thường.
~~~

có nhiều lỗ hổng:

- Secret có thể mang tên **credential**, **auth**, **access**, **private**, **client-key** hoặc một tên tùy ý.
- Một URL có thể chứa username/password dù key tên **endpoint**.
- Một cấu trúc JSON có thể chứa token bên trong.
- Map có key động.
- Secret có thể nằm trong String không có tên gợi ý.

**An toàn hơn:** diagnostic chỉ có một tập property logic được phép quan sát, và mặc định không in bất kỳ value nào.

### 23.1. Ví dụ allowlist

~~~java
public enum DiagnosticKey {
    GATEWAY_TIMEOUT("app.gateway.timeout"),
    GATEWAY_POOL_SIZE("app.gateway.pool.max-connections"),
    FEATURE_AUDIT("app.audit.enabled");

    private final String canonicalName;

    DiagnosticKey(String canonicalName) {
        this.canonicalName = canonicalName;
    }

    public String canonicalName() {
        return canonicalName;
    }
}
~~~

Một API dùng enum:

~~~java
SourceFinding inspect(
        ConfigurableEnvironment environment,
        DiagnosticKey key) {

    return SafeConfigProbe.inspect(
        environment,
        key.canonicalName()
    );
}
~~~

Như vậy caller không thể truyền một String tùy ý như **spring.datasource.password** nếu method public chỉ chấp nhận enum đã được review.

### 23.2. Đừng mở endpoint trả về toàn bộ enum nếu không cần

Ngay cả danh sách các key đang được phép kiểm tra có thể tiết lộ cấu trúc module. Áp dụng authorization và chỉ cung cấp các nhóm thông tin cần thiết cho vai trò được phép.

---

## 24. Quan sát source một cách có chủ đích trong application startup

Một diagnostic có thể chạy khi ứng dụng khởi động, nhưng không cần thiết phải xuất thông tin về mọi property ở mỗi lần chạy production.

Một mẫu tốt:

~~~text
On startup:
  - Log active profile category nếu được phép.
  - Log số lượng nguồn cấu hình.
  - Log tình trạng load của một vài nhóm cấu hình không nhạy cảm.
  - Không in raw config values.
  - Không liệt kê tất cả env variable names.
~~~

Nếu cần một lệnh hỗ trợ khi xảy ra sự cố, nên có cơ chế truy vấn nội bộ được bảo vệ và audit, thay vì tự xuất toàn bộ metadata vào log thường trực.

### 24.1. Không ghi origin path tự động mỗi lần chạy

Path và source URI có thể khác nhau giữa máy developer, CI và production; in vào log liên tục có thể lộ cấu trúc hạ tầng.

Có thể ghi một nhãn cấp cao như:

~~~text
winnerCategory=CONFIG_DATA
~~~

khi đã xác định category một cách an toàn.

---

## 25. Spring Profiles: một metadata có thể kiểm tra

Khi môi trường hoạt động sai, active profile thường là yếu tố đầu tiên cần kiểm tra.

Trong ConfigurableEnvironment:

~~~java
String[] profiles =
        environment.getActiveProfiles();
~~~

Nếu chính sách log cho phép, có thể ghi số lượng active profiles hoặc các tên profile chuẩn hóa như local/test/prod.

### 25.1. Tên profile có thể nhạy cảm

Một số tổ chức đưa tên môi trường, khách hàng hoặc dự án vào profile name. Vì thế không mặc định in toàn bộ getActiveProfiles() trong log production.

Nếu chỉ cần xác nhận prod:

~~~java
boolean prod =
        environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("prod")
        );
~~~

Sau đó log:

~~~text
productionProfileActive=true
~~~

Trạng thái boolean thường đủ cho câu hỏi cần giải.

### 25.2. Default profiles

Khi không có active profile, Spring Boot có thể áp dụng default profile và những tài liệu tương ứng.

Không nên tự suy ra rằng getActiveProfiles() rỗng nghĩa là không có Config Data được nạp. Cần hiểu default profiles và các source thực tế.

---

## 26. Sự khác biệt giữa cấu hình “có trong file” và “đã được bind”

Một file có:

~~~yaml
app:
  gateway:
    timeout: 5s
~~~

không bảo đảm:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout) {}
~~~

sẽ nhận timeout, vì prefix khác.

Tương tự, bean chưa đăng ký thì không có object cấu hình để đọc.

### 26.1. Chẩn đoán theo tầng

~~~text
Tầng 1: File/location/profile có được nạp?
Tầng 2: PropertySource có key canonical?
Tầng 3: Nguồn nào được ưu tiên?
Tầng 4: Binder có thể chuyển kiểu/nested object?
Tầng 5: Bean @ConfigurationProperties có được đăng ký?
Tầng 6: Validation có cho phép bean tồn tại?
Tầng 7: Service có sử dụng đúng bean và component?
~~~

Không dùng một phép dump Environment để thay thế việc phân biệt bảy tầng này.

### 26.2. Nếu Actuator env thấy key nhưng configprops không thấy

Có thể root cause thuộc prefix, bean registration, conditional creation, conversion hoặc validation. Không nhất thiết do một nguồn bị bỏ qua.

---

## 27. Chẩn đoán conversion an toàn

Giả sử:

~~~text
app.gateway.timeout = not-a-duration
~~~

Nếu giá trị này đến từ một môi trường thật và có thể chứa bí mật, đừng in raw value khi conversion fail.

Một test Binder có thể tái hiện với **giá trị mô phỏng**:

~~~java
Map<String, Object> testValues = Map.of(
        "app.gateway.timeout", "not-a-duration"
);

Binder testBinder = new Binder(
        new MapConfigurationPropertySource(testValues)
);
~~~

Sau đó assert lỗi conversion phù hợp.

### 27.1. Không cần sao chép dữ liệu production vào unit test

Nếu lỗi do chuỗi không thể chuyển thành Duration, dùng một input giả có cùng kiểu lỗi. Không đưa nguyên URL/token/password thật vào test fixture chỉ để tái hiện.

### 27.2. Một test có dữ liệu giả thường dễ chia sẻ hơn

Bộ test và code review có thể được nhìn thấy bởi nhiều thành viên. Việc thay giá trị thật bằng dữ liệu mô phỏng giúp tránh lộ secret qua repository, CI log hoặc artifact.

---

## 28. Kiểm thử helper không rò rỉ secret

Một unit test cho SafeConfigProbe có thể dùng một nguồn thử nghiệm chứa secret giả:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class SafeConfigProbeTest {

    @Test
    void reportsSourcePositionWithoutReturningValue() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
            new MapPropertySource(
                "unitTestSource",
                Map.of(
                    "app.gateway.timeout", "5s",
                    "app.gateway.api-key", "dummy-secret-do-not-log"
                )
            )
        );

        var finding = SafeConfigProbe.inspect(
            env,
            "app.gateway.timeout"
        );

        assertThat(finding.found()).isTrue();
        assertThat(finding.sourcePosition()).isPositive();
        assertThat(finding.originAvailable()).isFalse();
    }
}
~~~

Test này chỉ xác nhận metadata trả về. Nó không cố assert giá trị timeout, vì mục tiêu của helper là không tiết lộ value.

### 28.1. Test output redaction

Có thể thêm test capture log khi gọi một đường chẩn đoán hoàn chỉnh, rồi assert log **không chứa** chuỗi mô phỏng:

~~~text
dummy-secret-do-not-log
~~~

Không dùng một secret thật làm sentinel. Test phải bảo đảm các logger/appender được capture phù hợp, vì “không thấy trong một log” không chứng minh mọi hệ thống logging khác cũng an toàn.

### 28.2. Test key không nằm trong allowlist

Nếu API diagnostic chấp nhận enum hoặc registry, kiểm tra caller không thể yêu cầu một key bí mật không được phê duyệt. Đây là test về quyền truy cập/thiết kế API, khác với test về source position.

### 28.3. Không bật debug không kiểm soát trong test

Một framework test có thể tự in environment hoặc context khi startup fail. Nếu fixture chứa raw secret giả, hãy kiểm tra test report không dump toàn bộ exception hoặc source Map.

---

## 29. Không lộ secrets qua Actuator trong test

Một kiểm thử bảo mật có thể khởi động context với Actuator và xác nhận:

- env và configprops không bị expose ngoài dự kiến.
- Nếu được expose trong môi trường test riêng, access policy hoạt động.
- show-values=never thực sự che values.
- Người không được ủy quyền không xem được metadata nhạy cảm.
- Endpoint không hiển thị một secret mô phỏng trong HTTP response.

### 29.1. Test cả response và quyền truy cập

Một test chỉ tìm chuỗi ****** không đủ để kết luận endpoint an toàn. Nếu endpoint vẫn công khai toàn bộ key names/source names, có thể còn rủi ro metadata.

Một test chỉ assert HTTP 401 cũng chưa đủ nếu một cấu hình security khác trong production cho phép truy cập vô tình. Cần xét cấu hình security tương ứng và các nguồn build/deploy thực.

### 29.2. Không suy ra JMX an toàn từ test HTTP

Một ứng dụng có thể expose Actuator qua nhiều công nghệ. Nếu tổ chức dùng JMX từ xa, phải kiểm tra bảo mật trên kênh đó riêng.

---

## 30. Rủi ro trong tập trung log và observability pipeline

Kể cả khi code log ở console chỉ tồn tại tạm thời, một ứng dụng production có thể gửi log tới:

- Container runtime.
- Kubernetes logging agents.
- Hệ thống central logging.
- SIEM hoặc audit store.
- APM/tracing collector.
- Công cụ hỗ trợ vận hành và chatops.
- Hệ thống ticket hoặc bản chụp màn hình.

Một khi raw secret được log, nó có thể tồn tại lâu hơn thời gian cần thiết và được nhân bản qua nhiều kênh.

### 30.1. Cách phòng ngừa theo lớp

**Lớp 1:** Không đưa secret vào log từ source code.

**Lớp 2:** Dùng allowlist diagnostic, không dump Map/Environment.

**Lớp 3:** Áp dụng redaction ở logging pipeline nếu có.

**Lớp 4:** Giới hạn quyền xem log và retention.

**Lớp 5:** Khi phát hiện đã lộ, có quy trình thu hồi/rotate credential và xử lý incident.

**Không coi lớp 3 thay thế lớp 1.** Redaction bằng pattern có thể bỏ sót dữ liệu không được gắn nhãn secret.

### 30.2. Lệnh terminal cũng có rủi ro

Không chạy rồi copy nguyên output:

~~~bash
printenv
env
java -XX:+PrintFlagsFinal ...
~~~

chỉ để xác định một timeout. Với lệnh có thể hiển thị thông tin cấu hình hoặc process arguments, phải kiểm tra scope và chính sách chia sẻ.

---

## 31. Thông tin “an toàn để in” phải được xác định theo ngữ cảnh

Một API có thể coi timeout không nhạy cảm, nhưng source name của timeout lại chứa đường dẫn đến file có customer ID. Một system khác có thể coi cả tên feature flag là thông tin nội bộ không công khai.

Do đó không nên xây một helper “safe” chỉ vì nó không gọi getValue(). Cần:

1. Xác định người xem diagnostic.
2. Định nghĩa các property được phép hỏi.
3. Xác định metadata được phép trả.
4. Chuẩn hóa source name/path.
5. Bảo vệ endpoint/truy cập.
6. Có audit và thời hạn lưu trữ.
7. Test rò rỉ với dữ liệu mô phỏng.

**Bảo mật là thuộc tính của cả luồng dữ liệu, không chỉ một phương thức Java.**

---

## 32. Một runbook xử lý “giá trị không đúng”

Giả sử dịch vụ sử dụng timeout khác điều mong đợi.

### Bước 1. Khoanh vùng canonical key

Ví dụ:

~~~text
app.gateway.read-timeout
~~~

Đảm bảo prefix của @ConfigurationProperties và tên Java component tương ứng.

### Bước 2. Xác định bean có tồn tại

Kiểm tra registration: @ConfigurationPropertiesScan, @EnableConfigurationProperties hoặc phương án hợp lệ khác. Không in toàn bộ bean/toString.

### Bước 3. Xác định profile và nguồn cấu hình

Quan sát active profiles ở mức metadata an toàn và những source types đang có.

### Bước 4. Tìm nguồn thắng cho key canonical

Dùng helper dựa trên ConfigurationPropertySources, chỉ trả source position/category và originAvailable.

### Bước 5. Nếu nguồn thắng là CLI

Kiểm tra pipeline khởi động đã cấp một override không mong đợi, nhưng không in toàn bộ argv hoặc những tham số chứa secret.

### Bước 6. Nếu nguồn thắng là OS_ENV

Kiểm tra tên env canonical, chính sách inject và version deployment. Không dump env.

### Bước 7. Nếu nguồn thắng là CONFIG_DATA

Xem profile/import/location và origin metadata qua kênh bảo vệ. Không paste file path chứa tenant/user info vào ticket nếu không được phép.

### Bước 8. Nếu Binder/bean vẫn khác

Xem conversion, nested property path, List/Map, validation hoặc custom converter. Dùng test với dữ liệu giả để tái hiện.

### Bước 9. Xác nhận kết quả sau thay đổi

Đọc lại source position và tình trạng bean, chỉ test giá trị bằng một phép kiểm thử có quyền truy cập thích hợp thay vì dump ra log.

### Bước 10. Đóng quyền chẩn đoán tạm thời

Tắt logging tăng cường, gỡ exposure tạm nếu có, lưu báo cáo đã được lọc nội dung và kiểm tra không còn raw secret trong artifacts.

---

## 33. Runbook “thuộc tính không được nhận từ env”

Triệu chứng: operator khai báo biến môi trường nhưng bean vẫn dùng default.

Các nguyên nhân thường gặp:

- Tên env sai quy tắc chuyển canonical.
- Biến chưa được cấp cho tiến trình/container đang chạy.
- Container dùng phiên bản deployment cũ.
- Một CLI hoặc system property cao hơn đang ghi đè.
- @ConfigurationProperties prefix sai.
- Bean chưa đăng ký hoặc conversion failure.
- Config được đọc trước khi thay đổi nguồn.
- Test overrides che giá trị env.

### 33.1. Cách điều tra không lộ secret

Thay vì in env values, xác nhận:

~~~text
expectedNamePresent=true/false
canonicalKeyFound=true/false
winningSourceCategory=...
activeProfileCategory=...
beanBound=true/false
~~~

Nếu key bí mật, không log tên key cụ thể mà dùng mã nhóm đã được phê duyệt.

### 33.2. Khi đã biết nguồn thắng

Nếu nguồn thắng không phải env, tập trung vào precedence. Nếu nguồn thắng là env nhưng bean vẫn sai, tập trung conversion, property name adaptation, bean registration và lifecycle.

---

## 34. Runbook “Actuator báo một nguồn, bean nhận giá trị khác”

Có nhiều khả năng:

1. Bean được tạo trước khi một source động bị thêm.
2. Bean đã bind snapshot, sau đó Environment bị sửa.
3. Một property của bean đến từ key khác hoặc alias.
4. Có placeholder/conversion làm giá trị khác dạng raw.
5. Configprops trả metadata ở cấp bean không tương đương truy vấn một raw key.
6. Bean là record bất biến và không tự được rebind.
7. Có custom binder/handler/default logic.
8. Một collection được merge/replaced khác kỳ vọng.

### 34.1. Đừng suy luận refresh tự động

Việc Environment lúc này chứa một giá trị mới không đồng nghĩa những bean đã tạo được cập nhật.

Nếu ứng dụng có nhu cầu refresh, phải có cơ chế rebind/reconstruction phù hợp và test xác nhận, không chỉ sửa PropertySource.

### 34.2. Chẩn đoán bằng test thay vì log thật

Nếu nguyên nhân là List replacement hoặc conversion, một Binder/ApplicationContextRunner test với dữ liệu mô phỏng thường đủ tái hiện. Không cần bật show-values=always ở production.

---

## 35. Chẩn đoán nguồn config tree và mounted secrets

Trong container/kubernetes, thông tin cấu hình có thể được mount vào filesystem và nạp qua configtree:

~~~properties
spring.config.import=optional:configtree:/etc/config/
~~~

Giá trị có thể đến từ file, trong đó tên file là property name.

### 35.1. Không in file contents

Đừng đọc và log nội dung thư mục chỉ để kiểm tra một source có được nạp. Các file trong configtree có thể chứa secret.

Có thể kiểm tra tình trạng source presence/origin thông qua metadata, nhưng đường dẫn mount cũng có thể nhạy cảm. Hãy dùng nhãn như **CONFIG_TREE_SOURCE** thay vì in raw path.

### 35.2. Quyền filesystem vẫn quan trọng

Việc Spring Boot có thể bind secret không đồng nghĩa mọi diagnostic endpoint được phép hiển thị metadata về nó. Không để một API tùy ý đọc các configtree file names/paths nếu nó vượt quyền của người xem.

### 35.3. Source tồn tại không có nghĩa giá trị cuối từ source ấy

Một system property hoặc CLI có thể ghi đè key đã được configtree nạp. Chẩn đoán theo precedence, không chỉ theo file presence.

---

## 36. Chẩn đoán bằng kết quả phân loại, không bằng String value

Một output diagnostic lý tưởng có thể là một record nhỏ:

~~~java
public record ConfigDiagnosticResult(
        String diagnosticId,
        boolean configured,
        String sourceCategory,
        boolean originAvailable,
        String failureCategory
) {}
~~~

Ví dụ báo cáo:

~~~text
diagnosticId=GW_TIMEOUT
configured=true
sourceCategory=CONFIG_DATA
originAvailable=true
failureCategory=NONE
~~~

Dữ liệu này không chứa key nguyên văn, raw value hoặc file path. Nó cho phép nhóm vận hành trao đổi một kết luận kỹ thuật mà không cần truy cập secret.

### 36.1. Mã định danh không nên nhận input tùy ý

Đặt diagnosticId trong một enum hoặc registry do team kiểm soát. Không dùng request-supplied arbitrary property names.

### 36.2. SourceCategory chỉ nên có vài giá trị an toàn

Ví dụ:

~~~text
CLI
JVM
OS_ENV
CONFIG_DATA
DEFAULT
CUSTOM
UNKNOWN
~~~

Việc phân loại từ source name/class phải được test theo phiên bản Boot và những source tùy chỉnh. Nếu không chắc chắn, báo **UNKNOWN** thay vì in raw name.

### 36.3. Không tin bất kỳ chuỗi exception từ bên ngoài là an toàn

Nếu failureCategory lấy từ exception.getMessage(), nó có thể chứa raw input. Thay vì vậy, ánh xạ loại exception/sự cố sang một enum cố định.

---

## 37. Ví dụ phân loại lỗi an toàn

Một enum:

~~~java
public enum ConfigFailureCategory {
    NONE,
    SOURCE_NOT_FOUND,
    VALUE_NOT_CONVERTIBLE,
    VALIDATION_FAILED,
    BEAN_NOT_REGISTERED,
    CONFIG_DATA_NOT_LOADED,
    UNKNOWN
}
~~~

Cách báo:

~~~java
log.warn(
    "config diagnosticId={} failureCategory={}",
    "GW_TIMEOUT",
    ConfigFailureCategory.VALUE_NOT_CONVERTIBLE
);
~~~

Không viết:

~~~java
log.warn("Bad config: {}", exception.getMessage());
~~~

trong hệ thống nơi exception message có thể chứa dữ liệu đầu vào bí mật.

Trong log nội bộ có chính sách bảo vệ và nhu cầu điều tra đặc biệt, có thể lưu stack trace sau khi đánh giá rủi ro; nhưng không mặc định exception là dữ liệu không nhạy cảm.

---

## 38. Bảng so sánh công cụ chẩn đoán

| Công cụ | Thông tin chính | Có cần lưu ý secret? | Khi phù hợp |
| --- | --- | --- | --- |
| Environment.getProperty | Giá trị property sau giải quyết | Rất cao | Logic nghiệp vụ có quyền đọc, không log |
| Environment.getPropertySources | Danh sách nguồn | Có, cả source names | Xác định thứ tự và loại nguồn |
| PropertySource.containsProperty | Sự hiện diện exact key | Có giới hạn về relaxed binding | Probe cục bộ một key |
| ConfigurationPropertySources.from | Nguồn dưới góc nhìn binder | Không in returned value | Canonical key tracing có kiểm soát |
| ConfigurationProperty.getOrigin | Metadata nguồn gốc | File/path có thể nhạy cảm | Truy vết origin trong tooling bảo vệ |
| OriginLookup.getOrigin | Origin từ source hỗ trợ | Phụ thuộc key/source | Truy vết source cụ thể |
| /actuator/env | PropertySource/environment | Endpoint/metadata nhạy cảm | Quan sát có quyền, sanitized |
| /actuator/configprops | Bean configuration properties | Bound values có thể nhạy cảm | Kiểm tra bean sau bind |
| Binder unit test | Conversion/nested binding | Dùng dữ liệu giả | Tái hiện lỗi kỹ thuật |
| ApplicationContextRunner | Bean/validation/conditional | Dữ liệu test không thật | Tái hiện startup config behavior |
| @SpringBootTest | Config Data/profile/integration | Đừng dùng secret production | Xác nhận bootstrap/wiring |

**Một công cụ có khả năng xem raw value không có nghĩa người chẩn đoán phải sử dụng khả năng đó.**

---

## 39. Bài thực hành 1: chỉ liệt kê loại nguồn

Cho ConfigurableEnvironment của ứng dụng.

Yêu cầu: hiển thị số thứ tự và class name của những PropertySource, không in getSource(), getProperty(), toString() hoặc raw source name.

Đáp án tham khảo:

~~~java
int position = 0;

for (PropertySource<?> source :
        environment.getPropertySources()) {

    position++;

    System.out.printf(
        "%d: %s%n",
        position,
        source.getClass().getSimpleName()
    );
}
~~~

Bài mở rộng: thay class name bằng một enum source category an toàn theo allowlist.

## 40. Bài thực hành 2: canonical property và env var

Cho canonical key:

~~~text
app.client.read-timeout
~~~

Hãy viết tên biến môi trường chuẩn theo Spring Boot.

Đáp án:

~~~text
APP_CLIENT_READTIMEOUT
~~~

Dấu chấm thành underscore, dấu gạch ngang bị bỏ, rồi chuyển hoa. Không tự thêm underscore giữa read và timeout.

Bài mở rộng: giải thích vì sao **System.getenv().containsKey("APP_CLIENT_READTIMEOUT")** chỉ xác nhận biến hiện diện chứ không chứng minh đó là nguồn thắng.

## 41. Bài thực hành 3: chỉ lấy origin status

Cho một ConfigurationProperty đã được truy xuất từ ConfigurationPropertySource thích hợp.

Yêu cầu: báo có origin metadata hay không, không in origin.toString().

Đáp án:

~~~java
boolean available =
        property != null && property.getOrigin() != null;

log.debug("originAvailable={}", available);
~~~

Nếu origin null, không tự gán một file path đoán theo tên source.

## 42. Bài thực hành 4: Actuator giữ secrets được che

Một team muốn bật /actuator/env trong mạng nội bộ để xem source precedence, nhưng có password trong Environment.

Hỏi: có nên đặt show-values=always cho dễ chẩn đoán?

**Không.** Giữ show-values=never, giới hạn exposure/access và chỉ xem thông tin nguồn/key đã được phép. Nếu một người có quyền được phép xem giá trị thật ở trường hợp ngoại lệ, phải có quy trình bảo mật riêng, không thay đổi chính sách chung cho mọi người.

## 43. Bài thực hành 5: tránh log toString

Code:

~~~java
@ConfigurationProperties(prefix = "app.external")
public record ExternalProperties(
        String endpoint,
        String apiKey
) {}
~~~

Lệnh không nên dùng:

~~~java
log.info("{}", properties);
~~~

Vì record.toString có thể chứa apiKey. Hãy thay bằng:

~~~java
log.info("ExternalProperties bean loaded");
~~~

Nếu cần biết endpoint đã được cấu hình, dùng trạng thái có/không theo hợp đồng, không in apiKey và không in cả endpoint nếu URI có thể chứa credential.

## 44. Bài thực hành 6: nguồn thắng không phải origin mong đợi

application.yml có app.gateway.timeout=5s; profile prod có 8s; CLI có --app.gateway.timeout=15s.

Nếu một helper chỉ tìm origin của dòng trong application.yml rồi kết luận timeout cuối là 5s, điều gì sai?

**Sai ở precedence.** Origin cho biết một khai báo nằm ở đâu; không bảo đảm khai báo ấy được chọn làm giá trị cuối. Phải xác định nguồn ưu tiên cao nhất đang cung cấp key trước khi xem origin của đúng khai báo đó.

## 45. Bài thực hành 7: giả lập sự cố mà không dùng secret thật

Một deployment lỗi vì một giá trị lẽ ra là Duration nhưng được cấp sai dạng. Người vận hành định copy toàn bộ env var set vào repository issue.

Cách xử lý tốt hơn:

1. Xác định canonical key và loại lỗi conversion.
2. Tạo một input giả cùng kiểu lỗi, ví dụ **not-a-duration**.
3. Viết Binder test từ MapConfigurationPropertySource.
4. Xác nhận root cause conversion.
5. Báo cáo loại source thắng và trạng thái lỗi, không đưa raw config vào issue.

## 46. Bài thực hành 8: chọn diagnostic scope

Một API nội bộ nhận query parameter **key** rồi gọi:

~~~java
environment.getProperty(key)
~~~

và trả raw value cho người gọi.

Vấn đề: API trở thành công cụ xem mọi property mà tiến trình có quyền đọc, bao gồm secret.

Một thiết kế an toàn hơn:

- API nhận **diagnosticId** từ registry allowlist.
- Chỉ một tập nhỏ key không nhạy cảm được phép kiểm tra.
- Kết quả trả về source category và status, không trả raw value.
- API có authentication, authorization, rate limit và audit.
- Tên source/đường dẫn được chuẩn hóa.
- Nếu key không thuộc registry, từ chối.

---

## 47. Checklist trước khi xem nguồn cấu hình ở production

- [ ] Đã biết canonical property và prefix cần điều tra.
- [ ] Đã xác nhận người thực hiện có quyền chẩn đoán nhóm cấu hình đó.
- [ ] Không in Environment, System.getenv hoặc System.getProperties.
- [ ] Không dump PropertySource.getSource hoặc PropertySource.toString.
- [ ] Không gọi getProperty rồi log raw value.
- [ ] Không log record @ConfigurationProperties có secret bằng toString.
- [ ] Chỉ kiểm tra những key đã được cho phép.
- [ ] Đã phân biệt exact-key lookup với relaxed binding.
- [ ] Đã kiểm tra source precedence trước khi suy luận origin.
- [ ] Origin metadata có thể null; không tự tạo thông tin giả.
- [ ] Đã che hoặc lược bỏ resource path có tính nhạy cảm.
- [ ] /actuator/env và /actuator/configprops không được expose công khai.
- [ ] show-values giữ ở never nếu mục tiêu là chẩn đoán không in bí mật.
- [ ] JMX management, nếu bật, cũng được giới hạn quyền truy cập.
- [ ] Không bật TRACE/DEBUG toàn cục trên production chỉ để xem một key.
- [ ] Không copy raw env, CLI arguments hoặc JSON response vào ticket.
- [ ] Test sử dụng secret giả, không sử dụng credential thật.
- [ ] Báo cáo sự cố chỉ chứa mã nhóm, nguồn thắng và failure category.
- [ ] Các quyền/logging tăng cường tạm thời được gỡ sau điều tra.
- [ ] Nếu đã lộ secret, kích hoạt quy trình incident/rotation phù hợp.

## 48. Nguồn tài liệu tham khảo

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Actuator Endpoints và Sanitization: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot API — ConfigurationPropertySources: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertySources.html
- Spring Boot API — ConfigurationPropertySource: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertySource.html
- Spring Boot API — ConfigurationProperty: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/source/ConfigurationProperty.html
- Spring Boot API — OriginLookup: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/OriginLookup.html

Khi nâng cấp Spring Boot major version, cần đối chiếu lại vị trí API, cách cấu hình Actuator access/exposure và hành vi của các endpoint; không dựa vào một snippet cũ để bảo đảm tất cả trường hợp vẫn giống nhau.

---

## 49. Tổng kết

Khi một thuộc tính Spring Boot có giá trị không mong đợi, điều quan trọng thường là **vì sao nó được chọn**, không phải việc in giá trị của nó.

Cần ghi nhớ:

- **PropertySource** có thứ tự; nguồn cao hơn có thể che nguồn thấp hơn đối với cùng property.
- **ConfigurableEnvironment** và **Binder** có góc nhìn liên quan nhưng không đồng nhất, đặc biệt với relaxed binding và tên env.
- **ConfigurationPropertySources.from(...)** giúp quan sát canonical properties gần với cách Binder xử lý hơn exact-key lookup đơn giản.
- **ConfigurationProperty.getOrigin()** và **OriginLookup** có thể cung cấp metadata nguồn gốc, nhưng origin có thể null.
- **Origin không phải value**; dù vậy path/URI trong origin vẫn có thể nhạy cảm.
- **/actuator/env** và **/actuator/configprops** giúp chẩn đoán nhưng phải được bảo vệ; giữ show-values=never khi không cần raw values.
- Không in **System.getenv**, **System.getProperties**, **PropertySource.getSource**, bean **toString** hoặc raw configuration object.
- Không cho phép một diagnostic endpoint truy vấn tùy ý mọi key; dùng allowlist và quyền truy cập rõ.
- Phân biệt lỗi source/precedence với conversion, validation, bean registration và runtime refresh.
- Khi cần tái hiện lỗi, dùng test với giá trị giả thay vì copy bí mật production.
- Chẩn đoán an toàn nhất thường chỉ cần: **mã property được phép, nguồn thắng, originAvailable, loại lỗi và trạng thái bean**.

Nguyên tắc cuối cùng: **“Chẩn đoán nguồn cấu hình, không công bố dữ liệu cấu hình.”** Một hệ thống quan sát tốt cho biết property đến từ đâu và tại sao nó có hiệu lực, đồng thời không làm môi trường logging và vận hành trở thành nơi lưu giữ bí mật.
