# FailureAnalyzer và thông báo hướng dẫn xử lý lỗi khởi động

Khi một ứng dụng Spring Boot không thể khởi động, nguyên nhân thường nằm sâu trong chuỗi tạo ApplicationContext: thiếu bean, bind cấu hình thất bại, dependency không tương thích, cổng mạng đã được sử dụng, hoặc một thành phần không thể kết nối tới tài nguyên bắt buộc. Stack trace có thể chứa đầy đủ dữ liệu kỹ thuật, nhưng người vận hành vẫn phải tự tìm xem **điều gì đã sai và nên làm gì tiếp theo**.

Spring Boot cung cấp cơ chế **FailureAnalyzer** để biến một số lỗi khởi động thành báo cáo dễ đọc hơn. Một analyzer nhận exception, nhận diện trường hợp nó hiểu và trả về hai phần quan trọng:

- **Description:** mô tả rõ điều gì đã thất bại và ngữ cảnh liên quan.
- **Action:** hướng dẫn cụ thể người vận hành cách xử lý.

Ví dụ, thay vì chỉ thấy một BeanCreationException dài, ứng dụng có thể hiển thị:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

The application cannot create the tenant client because
the required tenant identifier is missing.

Action:

Set app.tenant.id in the active configuration and restart
the application. For a local run, use:
--app.tenant.id=demo
~~~

Bài học trình bày vòng đời xử lý lỗi của Spring Boot, vai trò của **FailureAnalyzer**, **AbstractFailureAnalyzer**, **FailureAnalysis** và **FailureAnalysisReporter**, cách viết analyzer tùy chỉnh, đăng ký analyzer để Boot phát hiện, kiểm thử cả nhánh nhận diện và không nhận diện exception, cùng các nguyên tắc tạo thông báo hướng dẫn hữu ích mà không làm lộ dữ liệu nhạy cảm.

## 1. Vì sao stack trace chưa đủ?

Stack trace trả lời câu hỏi: **exception xảy ra ở đâu và chuỗi lời gọi dẫn tới lỗi là gì?** Đây là thông tin cần thiết cho developer, nhưng không phải lúc nào cũng là cách tốt nhất để hướng dẫn vận hành.

Ví dụ một lỗi thiếu cấu hình có thể xuất hiện dưới dạng:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'tenantClient'
...
Caused by: java.lang.IllegalStateException:
tenant id must not be blank
...
~~~

Người đọc cần tự suy luận:

1. Bean nào không tạo được?
2. Giá trị nào đang thiếu?
3. Property key chính xác là gì?
4. Giá trị cần được đặt trong file nào hoặc nguồn nào?
5. Có thể sửa bằng command-line argument hay environment variable không?

FailureAnalyzer giúp đưa những thông tin này thành một báo cáo có cấu trúc.

### 1.1. Stack trace và FailureAnalysis phục vụ hai mục đích khác nhau

| Thông tin | Mục đích |
|---|---|
| Exception type | Phân loại loại lỗi ở tầng Java/framework. |
| Stack trace | Truy vết vị trí lỗi và call chain. |
| Root cause | Giải thích nguyên nhân sâu hơn trong chuỗi exception. |
| FailureAnalysis description | Tóm tắt sự cố bằng ngôn ngữ rõ ràng, có ngữ cảnh. |
| FailureAnalysis action | Đưa ra bước tiếp theo có thể thực hiện. |

FailureAnalysis **không thay thế exception**. Nó bổ sung một phần giải thích thân thiện hơn; exception vẫn có thể được giữ lại để chẩn đoán kỹ thuật.

### 1.2. Ví dụ các lỗi khởi động thường gặp

Một ứng dụng có thể thất bại khi:

- Không tìm thấy bean cần thiết để inject.
- Có nhiều bean cùng type và không thể chọn một candidate.
- Một property không chuyển đổi được sang kiểu yêu cầu.
- Cấu hình bắt buộc bị thiếu hoặc không hợp lệ.
- Port HTTP đã được process khác sử dụng.
- Không tìm thấy web server factory phù hợp.
- Không thể tạo DataSource hoặc kết nối tới dịch vụ bắt buộc.
- Một dependency không tương thích với phiên bản thư viện đang chạy.

Spring Boot đã có nhiều FailureAnalyzers tích hợp cho các tình huống phổ biến. Bạn chỉ nên viết analyzer riêng khi cần bổ sung **ngữ cảnh thuộc ứng dụng hoặc thư viện của mình** mà thông báo mặc định chưa diễn đạt đủ rõ.

## 2. FailureAnalyzer nằm ở đâu trong startup lifecycle?

Spring Boot khởi động ứng dụng thông qua SpringApplication. Trong quá trình đó, framework chuẩn bị Environment, tạo ApplicationContext, đăng ký bean definitions, refresh context và khởi tạo các thành phần cần thiết.

Nếu quá trình khởi động thất bại, SpringApplication xử lý lỗi và có thể yêu cầu FailureAnalyzers tìm một cách diễn giải phù hợp.

~~~text
SpringApplication.run(...)
          │
          ▼
Chuẩn bị Environment / Config Data
          │
          ▼
Tạo ApplicationContext
          │
          ▼
Đăng ký bean definitions
          │
          ▼
Refresh context / khởi tạo bean
          │
     ┌────┴─────┐
     │          │
  Thành công   Thất bại
     │          │
     ▼          ▼
Application   SpringApplication xử lý lỗi
ready                │
                      ▼
              FailureAnalyzer(s)
                      │
                      ▼
               FailureAnalysis
                      │
                      ▼
              FailureAnalysisReporter
                      │
                      ▼
             Báo cáo lỗi khi startup
~~~

Đây là sơ đồ khái niệm. Failure analysis được tích hợp trong cơ chế xử lý startup failure của Spring Boot; không phải mọi exception phát sinh trong suốt thời gian chạy ứng dụng đều tự động đi qua cơ chế này.

### 2.1. Analyzer cần hoạt động trước khi ApplicationContext sẵn sàng

FailureAnalyzer được dùng đúng lúc ứng dụng đang gặp lỗi trong quá trình khởi động. ApplicationContext có thể chưa refresh thành công, một số bean chưa được tạo, hoặc quá trình bootstrap đã thất bại trước khi có context hoàn chỉnh.

Vì vậy, một analyzer nên:

- Có logic nhận diện exception độc lập.
- Tránh phụ thuộc vào service/repository bean của ứng dụng.
- Không cần gọi database hoặc remote API để giải thích lỗi.
- Không giả định có thể dùng @Autowired như một Spring component thông thường.
- Không tự thực hiện hành động sửa cấu hình hoặc restart hệ thống.

Một analyzer tốt **quan sát và giải thích lỗi**, còn người vận hành hoặc cơ chế triển khai quyết định cách khắc phục.

### 2.2. FailureAnalyzer không phải @ControllerAdvice

Hai cơ chế xử lý lỗi ở hai thời điểm khác nhau:

| Cơ chế | Thời điểm | Ví dụ |
|---|---|---|
| FailureAnalyzer | Khi Spring Boot startup thất bại | Thiếu property, bean không tạo được, port đang bận. |
| @ControllerAdvice / @ExceptionHandler | Khi ứng dụng đã chạy và xử lý HTTP request | Request sai dữ liệu, resource không tồn tại, lỗi nghiệp vụ. |
| Error handling trong service | Trong quá trình thực thi logic | Retry, fallback, chuyển exception theo hợp đồng. |

Không dùng FailureAnalyzer để định dạng JSON error response cho một REST endpoint. Khi ứng dụng đã sẵn sàng, lỗi request thuộc cơ chế xử lý lỗi runtime.

### 2.3. Không phải mọi exception đều có FailureAnalysis

FailureAnalyzer có thể không nhận diện exception và trả về **null**. Khi đó Spring Boot vẫn cần xử lý lỗi theo cơ chế chung, và stack trace/exception information vẫn là nguồn chẩn đoán.

Không nên cố viết một analyzer tổng quát nhận mọi Throwable chỉ để luôn in ra một câu thông báo. Điều đó có thể che mất thông tin quan trọng hoặc đưa ra hướng dẫn sai.

## 3. FailureAnalyzer là interface nào?

Spring Boot cung cấp:

~~~java
org.springframework.boot.diagnostics.FailureAnalyzer
~~~

Interface có phương thức chính:

~~~java
FailureAnalysis analyze(Throwable failure);
~~~

Analyzer nhận exception gốc mà quá trình startup cung cấp và trả về:

- Một FailureAnalysis nếu nhận diện được trường hợp.
- **null** nếu không phải trường hợp analyzer phụ trách.

Ví dụ khái niệm:

~~~java
public final class MissingTenantFailureAnalyzer
        implements FailureAnalyzer {

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        if (failure instanceof MissingTenantException) {
            return new FailureAnalysis(
                    "Tenant configuration is missing.",
                    "Set app.tenant.id and restart.",
                    failure);
        }
        return null;
    }
}
~~~

Đoạn này minh họa hợp đồng, chưa xử lý exception bị bọc trong BeanCreationException. Trong ứng dụng thật, lỗi thường bị framework wrap bởi nhiều lớp exception; phần sau sẽ dùng AbstractFailureAnalyzer để tìm cause phù hợp.

### 3.1. Trả null có ý nghĩa gì?

Nếu analyzer không biết xử lý exception, nó nên trả null:

~~~java
@Override
public FailureAnalysis analyze(Throwable failure) {
    if (!isMyFailure(failure)) {
        return null;
    }

    return buildAnalysis(failure);
}
~~~

Trả null là cách báo cho cơ chế failure analysis rằng **analyzer này không cung cấp báo cáo cho lỗi hiện tại**. Nó không có nghĩa ứng dụng đã khắc phục được lỗi hoặc startup có thể tiếp tục.

### 3.2. Không ném exception mới từ analyzer

Analyzer được gọi trong lúc đang xử lý một startup failure. Nếu chính analyzer ném thêm exception do dereference null, đọc file hoặc gọi remote service, thông tin gốc có thể khó quan sát hơn.

Hãy giữ analyzer đơn giản, tránh side effects và bảo đảm trường hợp không nhận diện được luôn có thể trả null.

Nếu logic tạo thông báo có thể lỗi, hãy cân nhắc xử lý lỗi phụ một cách thận trọng và không làm mất startup exception ban đầu.

## 4. FailureAnalysis gồm những gì?

Class:

~~~java
org.springframework.boot.diagnostics.FailureAnalysis
~~~

Một FailureAnalysis có ba thông tin chính:

| Thành phần | Ý nghĩa |
|---|---|
| **description** | Điều gì đã thất bại? |
| **action** | Người vận hành nên làm gì? |
| **cause** | Throwable liên quan tới sự cố. |

Khởi tạo:

~~~java
FailureAnalysis analysis = new FailureAnalysis(
        "The tenant identifier is missing.",
        "Set app.tenant.id in the active configuration.",
        exception);
~~~

### 4.1. Description nên mô tả sự cố cụ thể

Thông báo yếu:

~~~text
Description:
Configuration error.
~~~

Thông báo tốt hơn:

~~~text
Description:
The tenant client could not be created because the
required property 'app.tenant.id' is missing.
~~~

Description nên giúp người đọc trả lời:

- Thành phần nào thất bại?
- Điều kiện nào không được đáp ứng?
- Có property, bean, resource hoặc dependency nào liên quan?

Tránh lặp lại nguyên văn exception class name nếu nó không giúp người vận hành hiểu tình huống.

### 4.2. Action phải đưa ra bước có thể thực hiện

Thông báo yếu:

~~~text
Action:
Check your configuration.
~~~

Thông báo cụ thể hơn:

~~~text
Action:
Set 'app.tenant.id' in the active configuration source.
For a local run, pass:
--app.tenant.id=demo
~~~

Một Action tốt có thể chỉ rõ:

1. Property key hoặc bean cần được cung cấp.
2. Nguồn cấu hình phù hợp.
3. Giá trị/định dạng được chấp nhận.
4. Lệnh hoặc bước kiểm tra tiếp theo.
5. Cách khởi động lại sau khi sửa.

Không đưa ra giá trị mẫu có thể vô tình trỏ vào production hoặc hệ thống bên ngoài thật.

### 4.3. Cause giữ lại thông tin kỹ thuật

~~~java
return new FailureAnalysis(
        description,
        action,
        cause);
~~~

Cause giúp báo cáo giữ mối liên hệ với exception. Tùy reporter và cấu hình logging, thông tin nguyên nhân/stack trace có thể được hiển thị thêm.

Không nên tạo một RuntimeException mới chỉ để làm cause nếu exception gốc đã có đầy đủ thông tin hữu ích. Giữ cause thực tế giúp chẩn đoán chính xác hơn.

## 5. FailureAnalysisReporter chịu trách nhiệm hiển thị báo cáo

FailureAnalyzer **không trực tiếp quyết định cách in báo cáo**. Spring Boot tách phần nhận diện lỗi khỏi phần trình bày thông qua:

~~~java
org.springframework.boot.diagnostics.FailureAnalysisReporter
~~~

Reporter nhận FailureAnalysis và quyết định cách đưa nó tới người vận hành.

Spring Boot có reporter mặc định ghi failure analysis qua logging. Trong startup failure thông thường, người dùng thường thấy một khối thông báo:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

...

Action:

...
~~~

### 5.1. Tách analyzer và reporter có lợi ích gì?

Một analyzer có thể tập trung vào:

- Nhận diện exception.
- Rút ra thông tin có ý nghĩa.
- Tạo description/action.

Reporter tập trung vào:

- In ra console/log.
- Chuyển báo cáo đến một nơi quan sát phù hợp nếu có custom integration.
- Quyết định cách định dạng output.

Nhờ vậy, logic giải thích lỗi không cần phụ thuộc vào terminal, logger hoặc hệ thống thu thập log cụ thể.

### 5.2. Khi nào cần custom reporter?

Phần lớn ứng dụng chỉ cần reporter mặc định. Custom reporter chỉ hợp lý khi có yêu cầu rõ ràng, chẳng hạn môi trường bootstrap đặc biệt hoặc cách trình bày failure analysis riêng.

Không nên gửi thông báo khởi động thất bại qua email, Slack hoặc remote service một cách mặc định: mạng có thể không sẵn sàng chính là nguyên nhân startup failure, và side effect bên ngoài có thể khiến quá trình báo lỗi tiếp tục thất bại.

### 5.3. Reporter không thay thế việc ghi nhận exception

Nếu custom reporter chỉ in description/action rồi bỏ cause, nhóm vận hành có thể mất dữ liệu kỹ thuật quan trọng.

Hãy cân nhắc:

- Giữ lại exception type và cause.
- Không in secret.
- Không tạo quá nhiều bản sao stack trace.
- Giữ output dễ tìm trong log startup.

Nếu không có yêu cầu cụ thể, nên dùng reporter mặc định của Spring Boot.

## 6. AbstractFailureAnalyzer giúp nhận diện exception trong cause chain

Trong thực tế, exception mà SpringApplication nhận được thường không phải custom exception trực tiếp.

Ví dụ:

~~~text
BeanCreationException
  └── IllegalStateException
       └── MissingTenantConfigurationException
~~~

Nếu chỉ viết:

~~~java
if (failure instanceof MissingTenantConfigurationException) {
    // ...
}
~~~

analyzer sẽ không nhận diện được khi exception ngoài cùng là BeanCreationException.

Spring Boot cung cấp:

~~~java
org.springframework.boot.diagnostics.AbstractFailureAnalyzer
~~~

Class này giúp tìm một cause thuộc kiểu exception mong muốn trong chuỗi cause, rồi gọi phương thức analyze tương ứng.

~~~java
public abstract class AbstractFailureAnalyzer<T extends Throwable>
        implements FailureAnalyzer {

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        // Tìm cause có kiểu T và chuyển cho subclass xử lý.
    }
}
~~~

Đây là mô tả rút gọn về ý tưởng; không phải implementation cần tự viết lại.

### 6.1. Khi nào nên kế thừa AbstractFailureAnalyzer?

Phù hợp khi:

- Bạn có một exception cụ thể do ứng dụng/thư viện định nghĩa.
- Exception có thể bị framework wrap.
- Muốn tập trung logic vào một loại cause.
- Không muốn tự duyệt getCause() và xử lý vòng lặp.

Ví dụ:

~~~java
public final class MissingTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                MissingTenantConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingTenantConfigurationException cause) {

        return new FailureAnalysis(
                "The tenant client cannot start because "
                        + "the tenant identifier is missing.",
                "Set 'app.tenant.id' in the active configuration "
                        + "and restart the application.",
                cause);
    }
}
~~~

**rootFailure** là exception ban đầu mà analyzer nhận; **cause** là exception đúng kiểu được tìm thấy trong chuỗi nguyên nhân.

### 6.2. Phân biệt rootFailure và cause

Trong ví dụ:

~~~java
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause)
~~~

- **rootFailure** có thể là BeanCreationException chứa nhiều ngữ cảnh Spring.
- **cause** là MissingTenantConfigurationException chứa thông tin lỗi thuộc ứng dụng.

Nếu description chỉ cần property key và tenant configuration, dùng cause là đủ. Nếu cần bean name hoặc thông tin từ exception ngoài, rootFailure có thể hữu ích.

Đừng mặc định cause là root cause cuối cùng theo mọi nghĩa. AbstractFailureAnalyzer tìm cause phù hợp theo kiểu generic của analyzer; một chuỗi exception có thể chứa nhiều loại cause.

### 6.3. Viết FailureAnalyzer trực tiếp khi cần logic đặc biệt

Nếu cần nhận diện nhiều loại exception hoặc quy tắc không phù hợp với một kiểu generic duy nhất, có thể implement FailureAnalyzer trực tiếp và duyệt cause chain có kiểm soát.

Ví dụ helper:

~~~java
static <T extends Throwable> T findCause(
        Throwable failure,
        Class<T> type) {

    Throwable current = failure;

    while (current != null) {
        if (type.isInstance(current)) {
            return type.cast(current);
        }
        current = current.getCause();
    }

    return null;
}
~~~

Trong code thực tế, cần cân nhắc chuỗi cause bất thường có vòng lặp; các exception Java thông thường không tạo vòng lặp như vậy nhưng analyzer tổng quát nên tránh giả định quá mức.

Nếu chỉ xử lý một exception type, **AbstractFailureAnalyzer** thường ngắn gọn và dễ hiểu hơn.

## 7. Xây dựng custom exception cho lỗi cấu hình thuộc ứng dụng

Giả sử một dịch vụ đa tenant bắt buộc có tenant ID để tạo client. Nếu thiếu tenant ID, ứng dụng không thể phục vụ request an toàn và nên thất bại ngay lúc startup.

Định nghĩa exception:

~~~java
package com.example.tenant;

public class MissingTenantConfigurationException
        extends RuntimeException {

    public MissingTenantConfigurationException() {
        super("The required tenant identifier is missing");
    }
}
~~~

Exception này thể hiện một tình huống cụ thể, có tên rõ nghĩa. Không nên dùng IllegalStateException chung chung cho mọi lỗi nếu thư viện cần cung cấp thông báo riêng cho từng loại.

### 7.1. Ném exception ở nơi phát hiện được điều kiện vi phạm

Ví dụ:

~~~java
package com.example.tenant;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.tenant")
public record TenantProperties(String id) {
}
~~~

Bean tạo client:

~~~java
package com.example.tenant;

public final class TenantClient {

    private final String tenantId;

    public TenantClient(String tenantId) {
        this.tenantId = tenantId;
    }

    public String tenantId() {
        return tenantId;
    }
}
~~~

Configuration:

~~~java
package com.example.tenant;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(TenantProperties.class)
public class TenantClientAutoConfiguration {

    @Bean
    TenantClient tenantClient(TenantProperties properties) {
        if (properties.id() == null
                || properties.id().isBlank()) {
            throw new MissingTenantConfigurationException();
        }

        return new TenantClient(properties.id());
    }
}
~~~

Ví dụ này minh họa một lỗi do application/library chủ động phát hiện. Trong một ứng dụng thực tế, nếu thiếu property là lỗi bind có thể phát hiện sớm hơn, **@Validated và Bean Validation** có thể phù hợp hơn để fail ngay ở bước binding. Custom exception hữu ích khi điều kiện phụ thuộc logic hoặc cần thông điệp thuộc domain.

### 7.2. Không đưa giá trị secret vào exception message

Exception:

~~~java
throw new MissingTenantConfigurationException();
~~~

chỉ mô tả key/điều kiện thiếu. Tránh:

~~~java
throw new IllegalStateException(
        "Tenant secret was invalid: " + secret);
~~~

Exception message có thể xuất hiện trong stack trace, log hoặc FailureAnalysis. Không đưa password, token, private key hoặc dữ liệu cá nhân vào message.

### 7.3. Phân biệt thiếu cấu hình với cấu hình sai định dạng

Có thể định nghĩa riêng:

~~~java
public class InvalidTenantConfigurationException
        extends RuntimeException {
    public InvalidTenantConfigurationException(String message) {
        super(message);
    }
}
~~~

Nếu cần thông báo hướng dẫn khác nhau:

- MissingTenantConfigurationException: chưa khai báo tenant ID.
- InvalidTenantConfigurationException: tenant ID có mặt nhưng không đúng định dạng được hỗ trợ.

Tách exception theo tình huống giúp analyzer tạo Action chính xác. Đừng tạo hàng chục exception chỉ để thay đổi một câu chữ nhỏ; chỉ tách khi nguyên nhân và cách khắc phục thực sự khác nhau.

## 8. Viết MissingTenantFailureAnalyzer

Tạo class:

~~~java
package com.example.tenant.diagnostics;

import com.example.tenant.MissingTenantConfigurationException;
import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class MissingTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                MissingTenantConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingTenantConfigurationException cause) {

        String description =
                "The tenant client cannot be created because "
                + "the required property 'app.tenant.id' is missing.";

        String action =
                "Set 'app.tenant.id' in the active configuration. "
                + "For a local run, pass "
                + "'--app.tenant.id=demo' and restart the application.";

        return new FailureAnalysis(
                description,
                action,
                cause);
    }
}
~~~

### 8.1. Vì sao analyzer không cần @Component?

FailureAnalyzer được Spring Boot phát hiện qua cơ chế factory discovery của framework, không cần chờ component scanning của ApplicationContext.

Analyzer có thể được gọi khi context chưa tạo thành công. Nếu chỉ đánh dấu @Component, bạn đang phụ thuộc vào một context có thể chưa hoàn tất việc scan/đăng ký bean.

Đối với custom FailureAnalyzer, hãy đăng ký theo cơ chế **SpringFactoriesLoader** mà Boot dùng cho loại extension này.

### 8.2. Một analyzer nên làm ít việc

Trong analyze():

- Đọc các thông tin đã có trên exception.
- Tạo description và action.
- Trả về FailureAnalysis.

Không nên:

- Tạo ApplicationContext mới.
- Tự chạy lại SpringApplication.
- Gọi database để xác minh cấu hình.
- Thực hiện HTTP request tới dịch vụ bên ngoài.
- Thay đổi file YAML hoặc environment variables.
- Tự restart process.

Lúc startup đã thất bại, các dependency bên ngoài có thể không sẵn sàng. Analyzer càng ít side effects thì càng đáng tin cậy khi được gọi trong tình huống sự cố.

### 8.3. Action nên chỉ ra nguồn cấu hình hợp lệ

Thông báo:

~~~text
Set app.tenant.id.
~~~

có thể chưa đủ với ứng dụng có nhiều nguồn cấu hình.

Có thể nói rõ:

~~~text
Set 'app.tenant.id' in the active Spring Boot configuration.
You can provide it in application.yml, an external Config Data
file, an environment variable, or a command-line argument.
~~~

Nếu môi trường có một quy ước deployment cụ thể, hướng dẫn nên phản ánh quy ước đó. Không cần liệt kê mọi nguồn cấu hình nếu một nguồn duy nhất được tổ chức vận hành cho phép.

## 9. Đăng ký FailureAnalyzer bằng META-INF/spring.factories

Để Spring Boot phát hiện custom analyzer, thêm file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer
~~~

Đây là metadata được đọc bởi cơ chế Spring factories.

### 9.1. Đường dẫn phải đúng

File cần nằm đúng trong resources:

~~~text
src/main/
└── resources/
    └── META-INF/
        └── spring.factories
~~~

Sau khi đóng gói, metadata phải nằm trong JAR dưới:

~~~text
META-INF/spring.factories
~~~

Nếu file chỉ nằm ở src/test/resources, analyzer có thể xuất hiện trong test classpath nhưng không được đóng gói vào artifact dùng khi chạy thật.

### 9.2. Không nhầm với AutoConfiguration.imports

Spring Boot 3 sử dụng file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

để đăng ký auto-configuration classes.

Đây là cơ chế khác với đăng ký FailureAnalyzer.

| Extension | Metadata thông thường |
|---|---|
| FailureAnalyzer | META-INF/spring.factories |
| FailureAnalysisReporter | META-INF/spring.factories |
| Auto-configuration class của Boot 3 | META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports |

Không đưa MissingTenantFailureAnalyzer vào AutoConfiguration.imports như thể nó là @AutoConfiguration.

### 9.3. Nếu spring.factories đã tồn tại

Một module có thể đã dùng spring.factories để đăng ký những extension khác. Hãy **thêm key/value** cho FailureAnalyzer, giữ nguyên các entries khác.

Ví dụ:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer

org.springframework.boot.diagnostics.FailureAnalysisReporter=\
com.example.tenant.diagnostics.CustomFailureAnalysisReporter
~~~

Ví dụ trên minh họa hai extension khác nhau. Không cần tự tạo CustomFailureAnalysisReporter nếu reporter mặc định đã đáp ứng nhu cầu.

### 9.4. Nhiều analyzer có thể được đăng ký

Nếu một thư viện có nhiều tình huống riêng:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer,\
com.example.tenant.diagnostics.InvalidTenantFailureAnalyzer
~~~

Mỗi analyzer nên nhận diện một phạm vi lỗi đủ rõ và trả null cho trường hợp ngoài phạm vi.

Tránh để nhiều analyzer cùng nhận diện một exception nhưng tạo ra thông báo mâu thuẫn. Nếu có các analyzer cạnh tranh, hãy xem xét cách Boot sắp xếp/áp dụng chúng theo phiên bản đang sử dụng và thiết kế exception type/điều kiện đủ cụ thể.

### 9.5. Analyzer cần có mặt trên runtime classpath

Nếu analyzer nằm trong một starter riêng, dependency của ứng dụng phải đưa artifact đó vào runtime classpath.

Một class compile thành công nhưng không nằm trong artifact/runtime classpath thì Spring Boot không thể phát hiện.

Khi chẩn đoán, kiểm tra:

- Class analyzer đã được đóng gói chưa?
- File META-INF/spring.factories có trong JAR không?
- Tên fully qualified class có chính xác không?
- Constructor có thể được tạo theo yêu cầu discovery không?
- Có exception trong quá trình load analyzer không?

## 10. Viết analyzer cho lỗi cấu hình không hợp lệ

Một ứng dụng có thể phân biệt thiếu tenant ID với tenant ID sai định dạng.

Exception:

~~~java
package com.example.tenant;

public class InvalidTenantConfigurationException
        extends RuntimeException {

    public InvalidTenantConfigurationException() {
        super("The tenant identifier has an unsupported format");
    }
}
~~~

Analyzer:

~~~java
package com.example.tenant.diagnostics;

import com.example.tenant.InvalidTenantConfigurationException;
import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class InvalidTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                InvalidTenantConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            InvalidTenantConfigurationException cause) {

        return new FailureAnalysis(
                "The configured tenant identifier does not match "
                        + "the supported format.",
                "Check 'app.tenant.id'. Use the tenant identifier "
                        + "issued by the platform and follow the "
                        + "documented format.",
                cause);
    }
}
~~~

Đăng ký cả hai analyzer trong spring.factories:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer,\
com.example.tenant.diagnostics.InvalidTenantFailureAnalyzer
~~~

Mỗi analyzer nhận diện một exception type riêng. Điều này giúp:

- Description không phải đoán nguyên nhân.
- Action phù hợp với từng loại lỗi.
- Unit test có thể kiểm tra riêng từng tình huống.
- Khi thư viện thay đổi, contract của mỗi lỗi dễ được bảo vệ hơn.

### 10.1. Khi một exception có nhiều nguyên nhân

Một lỗi khởi động có thể có nhiều exception lồng nhau:

~~~text
UnsatisfiedDependencyException
  └── BeanCreationException
       └── IllegalStateException
            └── InvalidTenantConfigurationException
~~~

AbstractFailureAnalyzer tìm cause phù hợp theo kiểu generic. Không cần kiểm tra từng wrapper Spring nếu nguyên nhân cụ thể đã được biểu diễn bằng custom exception.

### 10.2. Đừng dựa vào message text để nhận diện lỗi

Ví dụ dễ vỡ:

~~~java
if (failure.getMessage().contains("tenant id")) {
    // ...
}
~~~

Message có thể thay đổi theo phiên bản framework, locale hoặc cách wrap exception. Nó cũng có thể chứa dữ liệu người dùng.

Nên nhận diện theo **exception type**:

~~~java
extends AbstractFailureAnalyzer<
        MissingTenantConfigurationException>
~~~

Nếu bạn không sở hữu exception type, có thể cần analyzer trực tiếp hoặc phân tích một loại exception framework cụ thể. Khi đó hãy giới hạn phạm vi, kiểm tra cause/type và tránh phụ thuộc vào câu chữ không ổn định.

## 11. Thông báo hướng dẫn tốt cần có những đặc điểm nào?

FailureAnalysis có thể được in rất nổi bật ngay trên console khi startup thất bại. Hãy coi nó như thông báo dành cho người chịu trách nhiệm đưa dịch vụ trở lại trạng thái hoạt động.

Một thông báo hữu ích thường có:

1. **Tên thành phần:** bean, integration hoặc tính năng không khởi động được.
2. **Điều kiện thất bại:** thiếu property, sai định dạng, thiếu dependency hoặc tài nguyên không khả dụng.
3. **Nguyên nhân cụ thể:** key/port/type/location liên quan nếu an toàn để hiển thị.
4. **Hành động cụ thể:** bước cấu hình, cài dependency hoặc giải phóng tài nguyên.
5. **Phạm vi áp dụng:** local, test, staging hay production nếu thông tin đã xác định chắc chắn.
6. **Bước xác nhận:** cách kiểm tra lại sau khi sửa.

### 11.1. Description và Action không nên lặp lại nhau

Ví dụ chưa tốt:

~~~text
Description:
The tenant id is missing.

Action:
The tenant id is missing. Add the tenant id.
~~~

Tốt hơn:

~~~text
Description:
The tenant client cannot be initialized because
'app.tenant.id' has no value.

Action:
Provide a non-empty 'app.tenant.id' in the active
configuration source, then restart the application.
~~~

Description nói **điều gì đã xảy ra**. Action nói **người đọc nên làm gì**.

### 11.2. Hướng dẫn phải khớp nguyên nhân

Nếu lỗi là port 8080 đã được sử dụng, thông báo:

~~~text
Set server.port to another value or stop the process
that is already listening on port 8080.
~~~

cụ thể hơn:

~~~text
Check the configuration.
~~~

Nếu lỗi do thiếu driver database, hướng dẫn cài/đưa dependency phù hợp vào runtime classpath có ý nghĩa hơn việc đổi server.port.

Không nên dùng một Action chung cho mọi lỗi chỉ để giảm số lượng analyzer.

### 11.3. Chỉ nêu thông tin mà analyzer có thể chứng minh

Nếu analyzer biết property thiếu, có thể nói property thiếu.

Nếu analyzer không biết chính xác file cấu hình được dùng, không nên khẳng định:

~~~text
Edit /etc/order-api/application-prod.yml.
~~~

trừ khi deployment contract bảo đảm location đó.

Hướng dẫn tổng quát nhưng chính xác:

~~~text
Set 'app.tenant.id' in the active Spring Boot configuration
source, then restart the application.
~~~

### 11.4. Đưa ví dụ lệnh chỉ khi an toàn

Ví dụ local:

~~~bash
java -jar app.jar --app.tenant.id=demo
~~~

có thể hữu ích nếu giá trị demo là dữ liệu không nhạy cảm và môi trường local chấp nhận nó.

Không đưa một command chứa password, API token hoặc credential thật vào Action. Không khuyến nghị giá trị demo cho production nếu chưa có nguồn tenant ID chính thức.

## 12. Tạo báo cáo cho lỗi port đã được sử dụng

Spring Boot có analyzer tích hợp cho một số lỗi phổ biến như port đã được chiếm dụng. Ví dụ một web server cố khởi động trên port 8080 nhưng một process khác đang lắng nghe.

Mô tả thường hướng người vận hành:

- Xác định process đang sử dụng port.
- Dừng process đó nếu không còn cần.
- Hoặc cấu hình ứng dụng dùng một port khác.

Trong ứng dụng Linux, có thể dùng công cụ hệ thống để quan sát socket; trên Windows có công cụ tương ứng. Không nên đưa một câu lệnh OS-specific vào mọi môi trường nếu analyzer không biết hệ điều hành hoặc quyền của người vận hành.

### 12.1. Thay port bằng cấu hình Spring Boot

Ví dụ:

~~~yaml
server:
  port: 8081
~~~

Hoặc:

~~~bash
java -jar app.jar --server.port=8081
~~~

Ví dụ này minh họa một action có thể thực hiện. Trong production, việc đổi port còn phải đồng bộ service discovery, ingress, load balancer và health checks.

### 12.2. Không tự giải phóng port trong FailureAnalyzer

Analyzer không nên tự tìm process rồi kill để “sửa” lỗi port. Nó chỉ nên mô tả nguyên nhân và gợi ý hành động.

Tự động dừng một process khác có thể gây gián đoạn dịch vụ hoặc tác động nhầm workload.

## 13. Built-in FailureAnalyzers của Spring Boot

Spring Boot cung cấp các analyzer cho nhiều lỗi phổ biến. Tên cụ thể và tập trường hợp được hỗ trợ có thể thay đổi giữa các phiên bản.

Những nhóm tình huống thường có thông báo chẩn đoán:

| Nhóm lỗi | Hướng thông tin mà analyzer có thể cung cấp |
|---|---|
| Thiếu bean / dependency | Bean nào không tìm thấy và cách đăng ký dependency cần thiết. |
| Nhiều bean cùng type | Những candidate nào gây ambiguity và cách dùng @Primary/@Qualifier hoặc loại bỏ bean thừa. |
| Bind cấu hình | Property nào không bind được, giá trị/type liên quan. |
| Port đang được sử dụng | Port không thể bind và cách chọn port khác/giải phóng port. |
| Thiếu web server factory | Dependency/configuration cần thiết để chạy web application. |
| Bean definition conflict | Tên bean bị xung đột và những lựa chọn cấu hình liên quan. |

Đây là các nhóm minh họa, không phải danh sách đầy đủ hoặc cam kết rằng mọi trường hợp trong nhóm đều có một analyzer riêng ở mọi phiên bản.

### 13.1. Đọc thông báo mặc định trước khi viết custom analyzer

Nếu Spring Boot đã tạo một FailureAnalysis đủ rõ, không cần viết thêm analyzer chỉ để diễn đạt lại cùng nguyên nhân.

Custom analyzer có thể cần khi:

- Exception thuộc thư viện nội bộ hoặc domain riêng.
- Thông báo mặc định không biết property/bean name thuộc ứng dụng.
- Cần hướng dẫn hành động theo deployment contract cụ thể.
- Một lỗi kỹ thuật chung cần được diễn giải theo ngữ cảnh sản phẩm.

### 13.2. Không cố thay thế mọi analyzer mặc định

Một analyzer tùy chỉnh nhận quá rộng, ví dụ tất cả BeanCreationException, có thể cạnh tranh với analyzer tích hợp và đưa ra Action sai cho lỗi không liên quan.

Hãy dùng exception type riêng hoặc điều kiện nhận diện thật hẹp. Nếu chỉ cần thêm thông tin, có thể sửa nơi phát sinh exception để nó chứa cause có ý nghĩa hơn.

### 13.3. Version compatibility

Khi nâng Spring Boot version:

- Kiểm tra package/API của FailureAnalyzer và FailureAnalysis.
- Xác nhận cách đăng ký qua spring.factories còn được hỗ trợ cho extension này.
- Chạy tests với đúng version dependency management của dự án.
- Kiểm tra output startup failure thực tế.

Đừng suy luận rằng vì auto-configuration của Boot 3 dùng AutoConfiguration.imports nên mọi extension factory khác cũng chuyển sang file đó. FailureAnalyzer vẫn thuộc cơ chế factory discovery riêng của Spring Boot.

## 14. Phân biệt FailureAnalyzer với ApplicationContextInitializer và listeners

Một số extension cũng chạy trong giai đoạn bootstrap, nhưng mục đích khác nhau:

| Extension | Vai trò |
|---|---|
| ApplicationContextInitializer | Tùy chỉnh ApplicationContext trước khi refresh. |
| ApplicationListener | Lắng nghe các application events. |
| EnvironmentPostProcessor | Điều chỉnh Environment trước khi context được tạo/refresh theo lifecycle hỗ trợ. |
| FailureAnalyzer | Diễn giải startup exception thành FailureAnalysis. |
| FailureAnalysisReporter | Trình bày/ghi nhận FailureAnalysis. |

Không dùng FailureAnalyzer để thêm property vào Environment. Nếu cần nạp property source trước khi bean được tạo, hãy xem Config Data hoặc EnvironmentPostProcessor theo yêu cầu.

### 14.1. Analyzer không phải nơi retry startup

Nếu một database tạm thời chưa sẵn sàng, analyzer có thể giải thích lỗi kết nối và chỉ ra endpoint/timeout đã cấu hình (nếu an toàn).

Nhưng analyzer không phải nơi thực hiện retry vô hạn hoặc chờ database xuất hiện. Retry thuộc cơ chế connection/client, orchestration hoặc startup readiness policy.

### 14.2. Không dùng ApplicationReadyEvent để bắt startup failure

ApplicationReadyEvent chỉ được phát khi ứng dụng đã sẵn sàng theo lifecycle tương ứng. Nếu context refresh thất bại, event này không phải cơ chế xử lý lỗi phù hợp.

FailureAnalyzer được tích hợp vào luồng xử lý startup failure của SpringApplication, nên phù hợp hơn với yêu cầu giải thích nguyên nhân khởi động không thành công.

## 15. Unit test cho FailureAnalyzer

Một analyzer nên được kiểm thử như một lớp Java độc lập. Không cần khởi động toàn bộ web application chỉ để xác nhận description/action.

### 15.1. Test nhận diện đúng exception

~~~java
package com.example.tenant.diagnostics;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.tenant.MissingTenantConfigurationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.BeanCreationException;
import org.springframework.boot.diagnostics.FailureAnalysis;

class MissingTenantFailureAnalyzerTests {

    private final MissingTenantFailureAnalyzer analyzer =
            new MissingTenantFailureAnalyzer();

    @Test
    void createsActionableAnalysisForMissingTenant() {
        Throwable failure = new BeanCreationException(
                "tenantClient",
                new MissingTenantConfigurationException());

        FailureAnalysis analysis = analyzer.analyze(failure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .contains("app.tenant.id");
        assertThat(analysis.getAction())
                .contains("--app.tenant.id=demo");
        assertThat(analysis.getCause())
                .isInstanceOf(
                        MissingTenantConfigurationException.class);
    }
}
~~~

Test này chứng minh analyzer có thể tìm custom exception nằm bên trong BeanCreationException và trả về thông báo tương ứng.

### 15.2. Test trường hợp không nhận diện được

~~~java
@Test
void returnsNullForAnUnrelatedFailure() {
    FailureAnalysis analysis =
            analyzer.analyze(
                    new IllegalArgumentException("unrelated"));

    assertThat(analysis).isNull();
}
~~~

Đây là một test quan trọng. Analyzer chỉ nên xử lý lỗi thuộc phạm vi của nó; exception không liên quan phải được để cho analyzer khác hoặc cơ chế chung xử lý.

### 15.3. Test nhiều loại exception riêng

Với InvalidTenantFailureAnalyzer:

~~~java
@Test
void createsAnalysisForInvalidTenant() {
    FailureAnalysis analysis =
            new InvalidTenantFailureAnalyzer().analyze(
                    new InvalidTenantConfigurationException());

    assertThat(analysis).isNotNull();
    assertThat(analysis.getDescription())
            .contains("unsupported format");
    assertThat(analysis.getAction())
            .contains("app.tenant.id");
}
~~~

Tách test theo từng analyzer giúp thông báo có thể được sửa độc lập mà không làm hỏng các lỗi khác.

### 15.4. Test không nên phụ thuộc toàn bộ output formatting

Không nên khóa test vào toàn bộ dòng có dấu sao, khoảng trắng hoặc màu terminal. Những chi tiết trình bày thuộc reporter và có thể thay đổi theo phiên bản.

Đối với unit test analyzer, hãy kiểm tra:

- Analyzer có nhận đúng exception không?
- Description có thông tin cần thiết không?
- Action có hướng dẫn thực hiện được không?
- Cause có được giữ đúng không?
- Exception ngoài phạm vi có trả null không?

## 16. Kiểm tra exception thật trong ApplicationContextRunner

Unit test trực tiếp analyzer xác nhận logic phân tích. Có thể bổ sung một test context nhỏ để chắc chắn bean configuration thực sự ném ra exception mong muốn.

~~~java
package com.example.tenant;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class TenantClientStartupTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            TenantClientAutoConfiguration.class));

    @Test
    void startupFailsWhenTenantIdIsMissing() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                            MissingTenantConfigurationException.class);
        });
    }

    @Test
    void startupSucceedsWhenTenantIdIsProvided() {
        runner.withPropertyValues(
                    "app.tenant.id=demo")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(TenantClient.class);
                    assertThat(context.getBean(TenantClient.class)
                            .tenantId())
                            .isEqualTo("demo");
                });
    }
}
~~~

Test này xác minh điều kiện startup trong auto-configuration:

- Không có tenant ID → context thất bại với cause dự kiến.
- Có tenant ID → context tạo TenantClient.

### 16.1. ApplicationContextRunner không tự chạy FailureAnalyzer như SpringApplication

Đây là điểm cần phân biệt:

- ApplicationContextRunner hữu ích để kiểm thử **context startup** và lấy startup failure.
- Nó không phải một lần chạy đầy đủ qua SpringApplication failure handling/reporting lifecycle.
- Do đó, context runner test ở trên **không chứng minh** custom analyzer đã được Spring Boot phát hiện từ spring.factories và reporter đã in ra thông báo.

Ta có thể dùng startup failure từ runner để đưa vào analyzer trong một test kết hợp:

~~~java
@Test
void analyzesTheActualContextStartupFailure() {
    runner.run(context -> {
        assertThat(context).hasFailed();

        FailureAnalysis analysis =
                new MissingTenantFailureAnalyzer().analyze(
                        context.getStartupFailure());

        assertThat(analysis).isNotNull();
        assertThat(analysis.getAction())
                .contains("app.tenant.id");
    });
}
~~~

Đây vẫn là test **logic analyzer trên exception thực tế**, chưa kiểm tra factory discovery/reporter.

### 16.2. Không để test context thất bại làm cả test suite thất bại

ApplicationContextRunner giữ startup exception trong AssertableApplicationContext và cho phép callback kiểm tra nó. Vì vậy, một test có chủ đích xác nhận startup fail vẫn có thể pass.

Đừng viết @SpringBootTest cho một ứng dụng cố ý fail startup nếu không có harness thích hợp, vì test runner có thể coi lỗi khởi tạo context là lỗi test trước khi bạn có cơ hội kiểm tra.

## 17. Integration test để xác nhận analyzer được Spring Boot phát hiện

Unit test analyzer không xác nhận file spring.factories được đóng gói đúng. Đối với một starter hoặc thư viện phát hành cho consumer, cần một kiểm thử ở mức artifact/runtime.

Một quy trình smoke test:

1. Build JAR chứa analyzer và META-INF/spring.factories.
2. Kiểm tra metadata thực sự nằm trong artifact.
3. Chạy một ứng dụng mẫu có thể tạo đúng custom exception khi startup.
4. Cố ý bỏ app.tenant.id để startup thất bại.
5. Thu output startup.
6. Xác nhận có description/action do analyzer cung cấp.
7. Cấp app.tenant.id hợp lệ và xác nhận ứng dụng khởi động.

Ví dụ lệnh chạy:

~~~bash
java -jar tenant-demo.jar
~~~

Nếu không cung cấp tenant ID, output kỳ vọng có đoạn:

~~~text
APPLICATION FAILED TO START

Description:
The tenant client cannot be created because the required
property 'app.tenant.id' is missing.

Action:
Set 'app.tenant.id' in the active configuration...
~~~

Sau đó chạy:

~~~bash
java -jar tenant-demo.jar --app.tenant.id=demo
~~~

và xác nhận startup thành công.

### 17.1. Kiểm tra metadata trong JAR

Trên môi trường có công cụ JDK:

~~~bash
jar tf tenant-starter.jar
~~~

Tìm:

~~~text
META-INF/spring.factories
com/example/tenant/diagnostics/MissingTenantFailureAnalyzer.class
~~~

Executable JAR Spring Boot có thể chứa dependency JAR lồng bên trong BOOT-INF/lib. Vì vậy cần xác định analyzer thuộc artifact nào và kiểm tra đúng JAR chứa class/metadata, không chỉ kiểm tra outer executable JAR.

### 17.2. Một test consumer nhỏ có thể bắt lỗi đăng ký

Nếu starter được phát hành như dependency:

~~~text
tenant-starter.jar
       │
       ▼
consumer-demo application
       │
       ▼
SpringApplication.run(...)
       │
       ▼
startup failure được tạo có chủ đích
       │
       ▼
failure report phải chứa description/action tùy chỉnh
~~~

Đây là bằng chứng gần với hành vi người dùng thư viện hơn việc gọi analyzer trực tiếp bằng new.

### 17.3. Đừng giả định chỉ có một cách kiểm tra reporter

Nếu ứng dụng cần kiểm tra chính xác output reporter, có thể chạy một process con và capture stdout/stderr. Process con giúp tách biệt global logging state và startup lifecycle khỏi JVM đang chạy test.

Không nên phụ thuộc vào một số ký tự định dạng cố định nếu điều cần bảo vệ chỉ là description/action. Hãy xác định output contract cần thiết và tránh test quá mong manh theo phiên bản.

## 18. Kiểm thử việc đăng ký qua SpringFactoriesLoader

FailureAnalyzer được phát hiện thông qua Spring factories metadata. Có thể thêm một test xác nhận thư viện công bố analyzer đúng trong test/runtime classpath.

Ví dụ ý tưởng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalyzer;
import org.springframework.core.io.support.SpringFactoriesLoader;

class FailureAnalyzerRegistrationTests {

    @Test
    void registersMissingTenantAnalyzer() {
        List<FailureAnalyzer> analyzers =
                SpringFactoriesLoader.loadFactories(
                        FailureAnalyzer.class,
                        getClass().getClassLoader());

        assertThat(analyzers)
                .anyMatch(
                        MissingTenantFailureAnalyzer.class::isInstance);
    }
}
~~~

Đoạn code trên minh họa API Spring Framework 6 dùng SpringFactoriesLoader. Nếu dự án đang ở phiên bản Spring Framework khác, kiểm tra chữ ký API tương ứng với version dependency được quản lý.

Test này chỉ xác nhận **factory discovery trên classpath test**. Nó chưa chứng minh:

- Metadata được đóng gói vào đúng artifact phát hành.
- Consumer thực tế có dependency đó ở runtime.
- SpringApplication đã gọi analyzer cho startup failure cụ thể.
- Reporter đã trình bày output như mong muốn.

Vì vậy, test metadata và integration smoke test phục vụ hai mục đích khác nhau.

## 19. Nếu cần custom FailureAnalysisReporter

Phần lớn ứng dụng không cần thay reporter mặc định. Nhưng để hiểu kiến trúc, một reporter đơn giản có thể được hình dung như:

~~~java
package com.example.tenant.diagnostics;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalysisReporter;

public final class ConsoleFailureAnalysisReporter
        implements FailureAnalysisReporter {

    @Override
    public void report(FailureAnalysis analysis) {
        System.err.println("APPLICATION FAILED TO START");
        System.err.println();
        System.err.println("Description:");
        System.err.println(analysis.getDescription());
        System.err.println();
        System.err.println("Action:");
        System.err.println(analysis.getAction());
    }
}
~~~

Đăng ký:

~~~properties
org.springframework.boot.diagnostics.FailureAnalysisReporter=\
com.example.tenant.diagnostics.ConsoleFailureAnalysisReporter
~~~

Đây là ví dụ minh họa giao diện reporter, **không phải khuyến nghị thay reporter mặc định**. Một reporter tự viết có thể:

- Làm mất định dạng hoặc thông tin cause mà reporter mặc định cung cấp.
- Tạo output trùng nếu reporter mặc định vẫn được đăng ký.
- Ghi sai stream khiến log collector không nhận được.
- Tạo lỗi mới khi báo cáo startup failure.

Nếu muốn tùy biến output, hãy xác định chính sách reporter hiện có, cách Spring Boot phát hiện nhiều reporters trong version sử dụng và mục tiêu cụ thể. Đừng đăng ký reporter mới chỉ để đổi một dòng tiêu đề.

### 19.1. Reporter cũng cần không phụ thuộc application beans

Reporter được dùng trong cùng giai đoạn startup failure. Không nên yêu cầu một @Service bean hoặc database connection đã sẵn sàng để in thông báo.

Nếu reporter cần cấu hình, ưu tiên constructor đơn giản hoặc dữ liệu có thể đọc an toàn từ môi trường bootstrap; không giả định ApplicationContext đã hoàn chỉnh.

## 20. Tạo thông báo cho lỗi bind cấu hình

Spring Boot có cơ chế binding các property vào @ConfigurationProperties. Khi giá trị không chuyển đổi được hoặc vi phạm validation, startup có thể thất bại với exception từ tầng binding/validation.

Ví dụ:

~~~java
package com.example.payment;

import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotNull Duration timeout,
        @Positive int maxAttempts) {
}
~~~

application.yml:

~~~yaml
app:
  payment:
    timeout: not-a-duration
    max-attempts: 3
~~~

Giá trị timeout không thể chuyển đổi thành Duration, nên quá trình binding có thể thất bại.

### 20.1. Ưu tiên validation rõ ràng trước khi viết analyzer

Nếu lỗi là một property không hợp lệ, thường nên:

- Dùng kiểu dữ liệu phù hợp trong @ConfigurationProperties.
- Dùng Jakarta Bean Validation như @NotBlank, @NotNull, @Positive, @Min, @Max khi thích hợp.
- Đặt thông báo validation rõ ràng.
- Cung cấp default hợp lý nếu property thật sự không bắt buộc.

Spring Boot đã có chẩn đoán cho nhiều lỗi binding. Chỉ thêm FailureAnalyzer khi cần biến lỗi kỹ thuật chung thành hướng dẫn thuộc domain/deployment.

### 20.2. Một analyzer domain có thể giải thích ý nghĩa của property

Ví dụ, property có mặt nhưng giá trị không được hệ thống hỗ trợ:

~~~text
Description:
The configured payment mode 'legacy-x' is not supported
by this version of the application.

Action:
Set 'app.payment.mode' to one of the supported values:
'sandbox' or 'live'. Confirm the selected mode with the
deployment configuration before restarting.
~~~

Thông báo này hữu ích hơn một lỗi chuyển đổi hoặc IllegalArgumentException nếu người vận hành cần biết các giá trị hợp lệ.

### 20.3. Không lặp lại toàn bộ giá trị cấu hình trong báo cáo

Nếu property chứa credential, URL có query token hoặc dữ liệu nhạy cảm, không in nguyên giá trị vào Description.

Có thể nói:

~~~text
The configured payment credential is invalid or unavailable.
~~~

và:

~~~text
Verify that the required secret is mounted and that the
service account can read it. Do not paste the secret into logs.
~~~

Analyzer nên hướng dẫn cách kiểm tra an toàn, không đưa secret vào log để thuận tiện chẩn đoán.

## 21. Xử lý lỗi thiếu bean và nhiều bean

Spring Boot có thể cung cấp FailureAnalysis cho một số tình huống dependency injection phổ biến.

### 21.1. Thiếu bean

Ví dụ:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator calculator;

    public InvoiceService(TaxCalculator calculator) {
        this.calculator = calculator;
    }
}
~~~

Nếu không có bean TaxCalculator phù hợp, context không thể tạo InvoiceService.

Thông báo hướng dẫn có thể chỉ ra:

- Type cần được đăng ký.
- Bean nào đang yêu cầu dependency đó.
- Cách khai báo @Component/@Bean hoặc thêm auto-configuration/dependency phù hợp.

### 21.2. Nhiều bean cùng type

~~~java
@Bean
TaxCalculator localTaxCalculator() {
    return new LocalTaxCalculator();
}

@Bean
TaxCalculator regionalTaxCalculator() {
    return new RegionalTaxCalculator();
}
~~~

Nếu một service inject TaxCalculator mà không có qualifier/primary và không có quy tắc lựa chọn phù hợp, Spring có thể không xác định được candidate duy nhất.

Action có thể hướng người dùng:

- Đánh dấu bean mặc định bằng @Primary nếu có một lựa chọn mặc định rõ ràng.
- Dùng @Qualifier tại injection point nếu cần chọn implementation cụ thể.
- Loại bỏ bean không cần thiết.

### 21.3. Không viết analyzer tổng quát cho mọi BeanCreationException

BeanCreationException có thể đại diện cho rất nhiều nguyên nhân:

- Constructor ném exception.
- Dependency không tồn tại.
- Property bind thất bại.
- File resource không đọc được.
- Lỗi kết nối external system.
- Lỗi khởi tạo thư viện bên thứ ba.

Một analyzer bắt mọi BeanCreationException và luôn nói “kiểm tra component scan” sẽ hướng dẫn sai nhiều trường hợp.

Hãy nhận diện cause cụ thể hoặc để analyzer mặc định của Boot xử lý.

## 22. Phân tích exception chain đúng cách

Một lỗi khởi động thường được wrap nhiều lần:

~~~text
ApplicationContextException
  └── BeanCreationException
       └── UnsatisfiedDependencyException
            └── IllegalStateException
                 └── MissingTenantConfigurationException
~~~

### 22.1. Không chỉ nhìn exception ngoài cùng

Exception ngoài cùng thường mô tả thất bại ở tầng framework. Root/cause bên trong có thể mang thông tin domain quan trọng hơn.

AbstractFailureAnalyzer giúp tìm cause theo generic type, tránh phải kiểm tra từng lớp wrapper.

### 22.2. Khi có nhiều cause cùng kiểu

Một chuỗi cause có thể chứa nhiều exception cùng type. AbstractFailureAnalyzer tìm một cause phù hợp theo cơ chế của nó; nếu thông điệp cần phân biệt các vị trí khác nhau, có thể:

- Dùng các exception subtype riêng.
- Bổ sung thông tin an toàn vào exception.
- Implement FailureAnalyzer trực tiếp với logic tìm cause có chủ đích.

Không nên parse stack trace string để xác định bean hoặc property.

### 22.3. Suppressed exceptions không nhất thiết là cause

Java có thể gắn suppressed exceptions khi close resource thất bại trong try-with-resources. Suppressed exception không nhất thiết nằm trên chuỗi getCause().

Nếu startup failure phụ thuộc vào lỗi cleanup, analyzer chỉ duyệt cause chain có thể không thấy suppressed exception. Hãy giữ exception gốc và sử dụng stack trace/diagnostic phù hợp; đừng mặc định mọi exception liên quan đều là cause trực tiếp.

## 23. Logging và FailureAnalysis

Khi startup thất bại, thông báo FailureAnalysis thường được gửi qua reporter mặc định và logging system. Tuy nhiên, analyzer không nên tự log toàn bộ lỗi rồi reporter lại log thêm lần nữa.

Ví dụ không nên:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    log.error("Tenant config failed", rootFailure);

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set app.tenant.id.",
            cause);
}
~~~

Điều này có thể tạo output trùng, đặc biệt khi startup framework cũng ghi exception/analysis.

Nên:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set 'app.tenant.id' in the active configuration.",
            cause);
}
~~~

Để reporter chịu trách nhiệm trình bày. Nếu có nhu cầu log bổ sung, cần xác định rõ nơi ghi và tránh lặp stack trace.

### 23.1. Startup failure vẫn cần exit code khác 0

FailureAnalyzer không biến một startup failure thành startup success. Ứng dụng vẫn thất bại và launcher/orchestrator cần nhận biết process không khởi động được.

Trong CI/CD hoặc container orchestration:

- Process exit code cần được xử lý như thất bại.
- Không chỉ grep một dòng “APPLICATION FAILED TO START” rồi coi đó là toàn bộ trạng thái.
- Dùng health/readiness checks để quan sát trạng thái sau khi ứng dụng đã chạy.

### 23.2. FailureAnalysis không thay readiness/liveness probe

FailureAnalyzer xử lý lỗi startup. Kubernetes readiness/liveness probes và Actuator health endpoints phục vụ quan sát process/container trong thời gian chạy.

Không dùng analyzer để giải thích một pod đã khởi động nhưng về sau mất kết nối database. Trường hợp đó thuộc runtime monitoring, health checks và logging.

## 24. Hướng dẫn theo môi trường: local, test và production

Action nên phù hợp với môi trường đã biết, nhưng không nên đoán môi trường dựa trên tên hostname hoặc working directory.

### 24.1. Local development

Ví dụ:

~~~text
Action:
For a local run, add the following property to your
application-local.yml or pass it as a command-line argument:
--app.tenant.id=demo
~~~

Giá trị demo chỉ phù hợp nếu hệ thống local chấp nhận tenant giả lập.

### 24.2. Test

~~~text
Action:
Provide app.tenant.id in the test properties or test
configuration before starting the application context.
~~~

Không khuyến nghị dùng tenant production trong test chỉ để vượt qua startup validation.

### 24.3. Production

~~~text
Action:
Verify that the deployment supplies app.tenant.id through
the approved configuration source. Confirm the mounted
configuration/secret and restart the affected instance.
~~~

Không yêu cầu người vận hành sửa trực tiếp một file trong container nếu deployment quản lý file đó bằng ConfigMap, Secret hoặc hệ thống cấu hình trung tâm.

### 24.4. Không tự suy đoán active profile

Analyzer có thể đọc một exception nhưng không nhất thiết có Environment hoàn chỉnh. Đừng hard-code Action “edit application-prod.yml” chỉ vì ứng dụng thường chạy production.

Nếu analyzer thực sự được thiết kế để nhận Environment từ bootstrap một cách an toàn, phải có cơ chế cung cấp tường minh và test lifecycle. Còn trong thiết kế đơn giản, hãy hướng dẫn qua property key và nguồn cấu hình đang được deployment quản lý.

## 25. Thông báo lỗi và bảo mật

Startup error thường được ghi vào console, log collector, CI output và hệ thống giám sát. Một FailureAnalysis không phù hợp có thể làm lộ:

- Password hoặc token.
- Internal hostname, IP và topology.
- File path chứa tên người dùng hoặc thông tin nhạy cảm.
- Nội dung config nguyên bản.
- Request payload hoặc dữ liệu cá nhân.

### 25.1. Không đưa secret vào Description hoặc Action

Không:

~~~java
String action = "Use API key " + apiKey
        + " in your deployment environment.";
~~~

Nên:

~~~java
String action =
        "Verify that the required API key is available "
        + "from the approved secret source.";
~~~

### 25.2. Không ghi toàn bộ exception message nếu có dữ liệu nhạy cảm

Nếu custom exception được tạo từ input người dùng, message có thể chứa nội dung không an toàn. Analyzer nên tạo description từ các trường đã kiểm soát, thay vì nối trực tiếp exception.getMessage() trong mọi trường hợp.

### 25.3. Tránh thông báo quá chi tiết về hạ tầng nội bộ

Trong môi trường production, Action có thể nói:

~~~text
Verify the configured database endpoint and the service
account's access through the approved deployment tooling.
~~~

thay vì in mọi chi tiết connection string, subnet, username và credential.

Thông tin càng cụ thể càng hữu ích, nhưng chỉ nên hiển thị dữ liệu mà người đọc output được phép biết.

### 25.4. FailureAnalysis không phải nơi chứa remediation script tự động

Không nhúng script xóa file, kill process, sửa permission hoặc đổi production config vào Action với hàm ý người dùng nên chạy ngay mà chưa xác minh.

Action nên mô tả thao tác an toàn, có thể kiểm tra và phù hợp quyền của người vận hành.

## 26. Các bước điều tra khi custom FailureAnalyzer không hoạt động

Giả sử startup thất bại nhưng console chỉ hiện stack trace hoặc thông báo mặc định. Hãy kiểm tra theo từng lớp.

### Bước 1 — Xác nhận lỗi xảy ra trong startup lifecycle

FailureAnalyzer được Spring Boot gọi khi xử lý lỗi khởi động. Nếu lỗi xảy ra trong một HTTP request sau khi application đã ready, cần dùng exception handling, logging và monitoring runtime.

### Bước 2 — Xác nhận analyzer nhận đúng exception type

Nếu analyzer kế thừa:

~~~java
AbstractFailureAnalyzer<MissingTenantConfigurationException>
~~~

thì exception đó phải xuất hiện trong cause chain của startup failure.

Nếu chỉ có IllegalStateException với một message tương tự nhưng không chứa custom exception, analyzer sẽ không match.

### Bước 3 — Kiểm tra exception có bị wrap không

Nếu analyzer implement FailureAnalyzer trực tiếp và chỉ kiểm tra instanceof trên root failure, nó có thể bỏ sót BeanCreationException bao ngoài.

Dùng AbstractFailureAnalyzer cho một cause type cụ thể hoặc tự duyệt cause chain khi có lý do rõ ràng.

### Bước 4 — Kiểm tra metadata spring.factories

Đường dẫn đúng:

~~~text
META-INF/spring.factories
~~~

Key đúng:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer
~~~

Class name phải là fully qualified name. Nếu file có nhiều entries, không ghi đè mất những registrations khác.

### Bước 5 — Kiểm tra class nằm trên runtime classpath

Analyzer có thể compile trong module nhưng dependency không được đóng gói vào runtime artifact. Xem dependency scope và nội dung JAR.

### Bước 6 — Kiểm tra cách tạo instance

Spring factories loader cần tạo được analyzer. Dùng class public, concrete và constructor đơn giản; tránh constructor yêu cầu một application service chưa thể tồn tại.

### Bước 7 — Kiểm tra analyzer có ném exception không

Một analyzer bị lỗi khi tạo FailureAnalysis có thể làm luồng báo cáo lỗi phức tạp hơn. Giữ logic thuần, tránh truy cập null hoặc external resources.

### Bước 8 — Xác nhận analyzer trả FailureAnalysis thay vì null

Nếu type match nhưng code có thêm điều kiện phụ, kiểm tra điều kiện đó có loại case thật hay không.

### Bước 9 — Kiểm tra reporter

Nếu analyzer trả analysis nhưng output không như mong muốn, xem reporter nào được đăng ký và output được gửi đến logging/console nào.

### Bước 10 — Chạy một startup smoke test bằng đúng artifact

Một unit test gọi analyzer trực tiếp không kiểm tra việc discovery trong JAR. Hãy chạy consumer sample với cùng dependency/artifact như deployment.

## 27. Những lỗi thường gặp và cách xử lý

### 27.1. Đánh dấu @Component nhưng analyzer không được gọi

**Dấu hiệu:** class có @Component, code compile, nhưng startup report không có thông báo tùy chỉnh.

**Nguyên nhân:** FailureAnalyzer không được phát hiện thông qua component scanning thông thường; nó được đăng ký bằng Spring factories metadata.

**Cách xử lý:** thêm implementation vào META-INF/spring.factories với key org.springframework.boot.diagnostics.FailureAnalyzer.

### 27.2. Đặt analyzer trong AutoConfiguration.imports

**Dấu hiệu:** file imports có class analyzer nhưng Boot không xử lý như mong đợi.

**Nguyên nhân:** AutoConfiguration.imports đăng ký auto-configuration classes, không phải FailureAnalyzer.

**Cách xử lý:** đăng ký analyzer qua spring.factories; giữ auto-configuration ở metadata imports riêng của nó.

### 27.3. Analyzer không nhận diện exception bị wrap

**Dấu hiệu:** exception ngoài cùng là BeanCreationException, nhưng analyzer chỉ nhận custom exception trực tiếp.

**Nguyên nhân:** kiểm tra instanceof trên root failure mà không duyệt cause chain.

**Cách xử lý:** kế thừa AbstractFailureAnalyzer<T> hoặc triển khai cause traversal có chủ đích.

### 27.4. Analyzer luôn trả null

**Dấu hiệu:** không thấy custom description/action.

**Nguyên nhân:** cause type không có trong chain, condition phụ không match hoặc analyzer đang xử lý nhầm exception class.

**Cách xử lý:** test analyzer trực tiếp với exception chain thật lấy từ startup failure và xác nhận kết quả khác null.

### 27.5. Analyzer nhận mọi BeanCreationException

**Dấu hiệu:** lỗi database, missing bean hoặc resource cũng bị báo “tenant configuration missing”.

**Nguyên nhân:** analyzer nhận exception quá rộng và suy luận nguyên nhân từ wrapper chung.

**Cách xử lý:** nhận diện custom exception hoặc cause/type cụ thể. Trả null với trường hợp không thuộc phạm vi.

### 27.6. Description chỉ ghi “Startup failed”

**Dấu hiệu:** người vận hành vẫn phải đọc stack trace để hiểu vấn đề.

**Nguyên nhân:** description không chỉ ra component/property/condition.

**Cách xử lý:** mô tả sự cố cụ thể bằng thông tin analyzer có thể chứng minh.

### 27.7. Action chỉ ghi “Check configuration”

**Dấu hiệu:** người đọc không biết key nào hoặc nguồn nào cần sửa.

**Nguyên nhân:** Action quá chung chung.

**Cách xử lý:** ghi property key, giá trị/format hợp lệ, nguồn cấu hình hoặc bước xác minh phù hợp.

### 27.8. Analyzer gọi database hoặc HTTP service

**Dấu hiệu:** quá trình báo lỗi lại timeout hoặc ném exception thứ hai.

**Nguyên nhân:** analyzer phụ thuộc hệ thống bên ngoài, có thể chính hệ thống đó đang gây startup failure.

**Cách xử lý:** chỉ phân tích exception và dữ liệu đã có. Không thực hiện network calls trong analyzer.

### 27.9. Analyzer dùng @Autowired service

**Dấu hiệu:** analyzer không khởi tạo được hoặc dependency chưa sẵn sàng.

**Nguyên nhân:** analyzer được gọi trong bootstrap failure lifecycle, ApplicationContext có thể chưa hoàn chỉnh.

**Cách xử lý:** thiết kế analyzer độc lập, stateless, constructor đơn giản; truyền thông tin cần thiết qua exception.

### 27.10. File spring.factories chỉ nằm trong test resources

**Dấu hiệu:** test classpath phát hiện analyzer nhưng executable JAR không có.

**Nguyên nhân:** metadata nằm trong src/test/resources thay vì src/main/resources.

**Cách xử lý:** đặt metadata production trong src/main/resources/META-INF/spring.factories và kiểm tra artifact đã build.

### 27.11. Ghi đè entries của spring.factories

**Dấu hiệu:** thêm FailureAnalyzer xong một extension factory khác biến mất.

**Nguyên nhân:** thay toàn bộ file hoặc thay value của key cũ không chủ ý.

**Cách xử lý:** merge key/value, giữ những entries đang tồn tại; kiểm tra metadata khi đóng gói.

### 27.12. Constructor analyzer yêu cầu application bean

**Dấu hiệu:** Spring factories loader không thể tạo analyzer.

**Nguyên nhân:** constructor yêu cầu service/repository mà ApplicationContext chưa tạo.

**Cách xử lý:** bỏ dependency runtime; dùng constructor không tham số hoặc chỉ dữ liệu có sẵn, ổn định.

### 27.13. Hai analyzer đưa ra hướng dẫn mâu thuẫn

**Dấu hiệu:** một lỗi được diễn giải theo nhiều cách hoặc kết quả không ổn định sau khi thêm dependency.

**Nguyên nhân:** phạm vi nhận diện chồng lấn.

**Cách xử lý:** thu hẹp exception type/conditions, tránh nhiều analyzer cùng nhận diện một lỗi. Kiểm tra discovery/ordering theo Spring Boot version.

### 27.14. Custom reporter làm mất thông tin mặc định

**Dấu hiệu:** output chỉ còn description/action, stack trace hoặc formatting trước đây biến mất.

**Nguyên nhân:** reporter tự viết thay thế hoặc bổ sung không đúng cách.

**Cách xử lý:** nếu không có nhu cầu rõ ràng, dùng reporter mặc định. Nếu custom, xác định output contract và test integration.

### 27.15. Dùng FailureAnalyzer để xử lý lỗi HTTP runtime

**Dấu hiệu:** analyzer không được gọi khi một request trả HTTP 500.

**Nguyên nhân:** FailureAnalyzer dành cho startup failure, không phải exception handler sau khi app ready.

**Cách xử lý:** dùng @ControllerAdvice, @ExceptionHandler, service error handling và observability runtime.

### 27.16. Test context runner không thấy output analyzer

**Dấu hiệu:** context runner có startup failure nhưng không có khối APPLICATION FAILED TO START.

**Nguyên nhân:** ApplicationContextRunner kiểm tra context startup; nó không chạy toàn bộ SpringApplication failure analysis/reporting lifecycle.

**Cách xử lý:** unit test analyzer riêng, context runner test exception, và startup smoke test với SpringApplication/process thật khi cần kiểm tra discovery/reporting.

### 27.17. Action đề xuất giá trị giả cho production

**Dấu hiệu:** người vận hành copy command mẫu và kết nối tới tenant/database không đúng.

**Nguyên nhân:** ví dụ local được trình bày như hướng dẫn production.

**Cách xử lý:** đánh dấu rõ giá trị demo chỉ dùng local/test; production phải lấy giá trị từ nguồn quản lý chính thức.

### 27.18. Thông báo in secret hoặc nội dung exception không an toàn

**Dấu hiệu:** startup logs chứa API key, credential hoặc dữ liệu cá nhân.

**Nguyên nhân:** analyzer nối trực tiếp exception message hoặc property value vào FailureAnalysis.

**Cách xử lý:** tạo message từ các trường đã kiểm soát, redaction và hướng dẫn xác minh secret mà không in giá trị.

### 27.19. Mong đợi analyzer tự sửa cấu hình

**Dấu hiệu:** startup vẫn fail sau khi có FailureAnalysis.

**Nguyên nhân:** nhầm analyzer là remediation engine.

**Cách xử lý:** FailureAnalyzer chỉ chẩn đoán và hướng dẫn. Người vận hành/deployment pipeline cần sửa cấu hình rồi khởi động lại.

### 27.20. Nâng Spring Boot nhưng quên kiểm tra metadata discovery

**Dấu hiệu:** code analyzer compile nhưng khi chạy version mới không có report tùy chỉnh.

**Nguyên nhân:** dependency graph, factory metadata hoặc cách đóng gói đã thay đổi.

**Cách xử lý:** chạy registration test và startup smoke test bằng đúng Spring Boot version được triển khai.

## 28. Những hiểu nhầm cần tránh

**“FailureAnalyzer thay thế stack trace.”**  
Không. Nó bổ sung description/action; exception vẫn cần thiết cho chẩn đoán kỹ thuật.

**“FailureAnalyzer xử lý mọi exception trong runtime.”**  
Không. Nó được dùng trong luồng xử lý startup failure của Spring Boot.

**“Chỉ cần @Component là Boot sẽ phát hiện analyzer.”**  
Không. Hãy đăng ký bằng Spring factories metadata.

**“AutoConfiguration.imports là nơi đăng ký tất cả extension.”**  
Không. FailureAnalyzer dùng spring.factories; AutoConfiguration.imports dành cho auto-configuration classes.

**“Analyzer phải tự duyệt mọi wrapper exception.”**  
Không. AbstractFailureAnalyzer<T> hỗ trợ tìm cause theo kiểu exception mong muốn.

**“Không nhận diện được lỗi thì nên trả một FailureAnalysis chung.”**  
Không. Trả null để analyzer khác hoặc cơ chế chung xử lý.

**“Description và Action có thể là cùng một câu.”**  
Không nên. Description mô tả sự cố; Action đưa ra bước khắc phục.

**“FailureAnalyzer có thể inject mọi Spring service.”**  
Không nên giả định như vậy. Nó hoạt động trong giai đoạn context có thể chưa hoàn chỉnh.

**“Một lỗi thiếu bean luôn cần custom analyzer.”**  
Không. Spring Boot đã có thông báo cho nhiều lỗi phổ biến. Chỉ bổ sung khi cần ngữ cảnh riêng.

**“ApplicationContextRunner test pass nghĩa reporter đã được gọi.”**  
Không. Runner kiểm tra context startup, còn SpringApplication có luồng xử lý/reporting startup failure riêng.

**“FailureAnalysisReporter phải được custom để dùng analyzer.”**  
Không. Reporter mặc định thường đủ cho hầu hết ứng dụng.

**“Analyzer có thể tự kill process chiếm port hoặc sửa file config.”**  
Không. Nó nên cung cấp chẩn đoán và hướng dẫn; remediation cần được kiểm soát riêng.

**“Càng nhiều chi tiết trong thông báo càng tốt.”**  
Không. Chỉ hiển thị dữ liệu cần thiết và được phép biết; không ghi secret hoặc hạ tầng nhạy cảm.

## 29. Quy trình thiết kế một FailureAnalyzer mới

Khi một lỗi startup thuộc domain của ứng dụng và thông báo mặc định chưa đủ hữu ích, có thể triển khai theo các bước sau.

### Bước 1 — Xác định lỗi có thực sự thuộc startup không

Nếu lỗi xảy ra sau khi app ready, dùng runtime exception handling và observability. FailureAnalyzer dành cho startup failure.

### Bước 2 — Tìm thông báo mặc định trước

Chạy ứng dụng trong một môi trường tái hiện được lỗi và đọc FailureAnalysis hiện tại. Nếu Boot đã chỉ ra đúng nguyên nhân và hành động, không cần custom analyzer.

### Bước 3 — Định nghĩa exception có ý nghĩa

Ví dụ:

~~~java
MissingTenantConfigurationException
~~~

Exception nên biểu diễn một điều kiện cụ thể và giữ nguyên cause nếu được bọc từ một lỗi thấp hơn.

### Bước 4 — Kế thừa AbstractFailureAnalyzer

~~~java
public final class MissingTenantFailureAnalyzer
        extends AbstractFailureAnalyzer<
                MissingTenantConfigurationException> {
    // Tạo FailureAnalysis từ cause đã nhận diện.
}
~~~

Chọn đúng exception type để tránh nhận diện quá rộng.

### Bước 5 — Viết Description và Action

Description nói rõ component/condition thất bại. Action nêu property key, nguồn cấu hình hoặc bước xử lý cụ thể. Không in secret và không đoán môi trường.

### Bước 6 — Đăng ký qua spring.factories

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.tenant.diagnostics.MissingTenantFailureAnalyzer
~~~

Đặt trong src/main/resources/META-INF/spring.factories của artifact cung cấp analyzer.

### Bước 7 — Unit test analyzer

Kiểm tra:

- Cause phù hợp → FailureAnalysis khác null.
- Description/action chứa thông tin cần thiết.
- Cause được giữ đúng.
- Exception ngoài phạm vi → null.

### Bước 8 — Context test lỗi thật

Dùng ApplicationContextRunner để tạo startup failure và xác nhận exception chain chứa custom exception. Có thể đưa failure đó vào analyzer để test logic với wrapper thực tế.

### Bước 9 — Test discovery/reporting ở mức artifact

Kiểm tra spring.factories trong JAR và chạy một consumer process với SpringApplication để xác nhận Boot gọi analyzer và reporter tạo output.

### Bước 10 — Bảo đảm thông báo an toàn

Kiểm tra Action không hướng người dùng tới credential demo ở production, không in secret và không khuyến khích thao tác phá hoại tự động.

### Sơ đồ quyết định

~~~text
Startup failure xảy ra
          │
          ▼
Boot có thông báo mặc định đủ rõ?
          │
      ┌───┴────┐
      │        │
     Có       Không
      │        │
      ▼        ▼
Dùng report   Có exception domain cụ thể?
hiện có             │
                ┌───┴────┐
                │        │
               Có       Không
                │        │
                ▼        ▼
        Custom Failure  Cải thiện exception
        Analyzer        hoặc dùng analyzer mặc định
                │
                ▼
       Unit + context + discovery tests
                │
                ▼
       Startup smoke test bằng artifact
~~~

## 30. Bài tập tự luyện

### Bài tập 1 — Nhận diện exception bị wrap

Một startup failure có chuỗi:

~~~text
BeanCreationException
  └── IllegalStateException
       └── MissingTenantConfigurationException
~~~

Analyzer kế thừa AbstractFailureAnalyzer<MissingTenantConfigurationException>.

**Câu hỏi:** Có cần tự kiểm tra BeanCreationException trước không?

**Đáp án định hướng:** Không. AbstractFailureAnalyzer hỗ trợ tìm cause có kiểu generic cần xử lý trong cause chain. Subclass nhận rootFailure và cause đã match.

### Bài tập 2 — Khi nào trả null?

Analyzer nhận MissingTenantConfigurationException nhưng startup failure là PortInUseException.

**Câu hỏi:** Analyzer nên làm gì?

**Đáp án:** Không nhận diện được trường hợp này nên trả null, để analyzer khác hoặc cơ chế chung xử lý.

### Bài tập 3 — Chọn thông báo tốt hơn

Thông báo A:

~~~text
Description: Startup failed.
Action: Check configuration.
~~~

Thông báo B:

~~~text
Description:
The tenant client cannot be created because
'app.tenant.id' is missing.

Action:
Set a non-empty 'app.tenant.id' in the active
configuration source, then restart the application.
~~~

**Câu hỏi:** Vì sao B hữu ích hơn?

**Đáp án định hướng:** B chỉ ra component, property và hành động cụ thể. A không giúp người vận hành thu hẹp phạm vi điều tra.

### Bài tập 4 — Đăng ký analyzer

Bạn đặt class trong package:

~~~text
com.example.payment.diagnostics.PaymentFailureAnalyzer
~~~

**Câu hỏi:** Metadata cần khai báo ở đâu?

**Đáp án:** Trong src/main/resources/META-INF/spring.factories với key org.springframework.boot.diagnostics.FailureAnalyzer và fully qualified class name.

### Bài tập 5 — Phân biệt metadata

**Câu hỏi:** Vì sao không đăng ký FailureAnalyzer trong AutoConfiguration.imports?

**Đáp án:** AutoConfiguration.imports dùng để phát hiện auto-configuration classes. FailureAnalyzer được tải qua Spring factories metadata riêng.

### Bài tập 6 — Test back-off của analyzer

Unit test gọi:

~~~java
analyzer.analyze(new IllegalArgumentException("other"))
~~~

và nhận null.

**Câu hỏi:** Điều đó có nghĩa analyzer lỗi không?

**Đáp án:** Không. Đây là hành vi đúng nếu IllegalArgumentException không thuộc phạm vi mà analyzer phụ trách.

### Bài tập 7 — Phân biệt context test và startup report

ApplicationContextRunner báo context startup failed và có startup exception, nhưng không thấy khối APPLICATION FAILED TO START.

**Câu hỏi:** Có thể kết luận FailureAnalyzer không được đăng ký không?

**Đáp án:** Chưa. ApplicationContextRunner không chạy toàn bộ SpringApplication failure reporting lifecycle. Hãy test analyzer trực tiếp và dùng một SpringApplication/process smoke test để xác nhận discovery/reporting.

### Bài tập 8 — Xử lý lỗi có secret

Custom exception chứa API key trong message.

**Câu hỏi:** Có nên đưa exception.getMessage() nguyên văn vào Description không?

**Đáp án:** Không. Tạo description từ thông tin đã kiểm soát, không in secret. Action nên hướng người vận hành kiểm tra nguồn secret mà không tiết lộ giá trị.

## Ghi nhớ cốt lõi

**FailureAnalyzer** là cơ chế Spring Boot dùng để biến startup exception thành một **FailureAnalysis** dễ hiểu hơn. Analyzer nhận diện lỗi và tạo hai phần: **Description** nói điều gì đã thất bại, **Action** hướng dẫn bước xử lý cụ thể. **AbstractFailureAnalyzer<T>** đặc biệt hữu ích khi exception domain bị bọc trong BeanCreationException hoặc những wrapper khác, vì nó tìm cause theo kiểu mong muốn.

Custom analyzer cần được đăng ký qua **META-INF/spring.factories** với key **org.springframework.boot.diagnostics.FailureAnalyzer**. Không nhầm metadata này với AutoConfiguration.imports của auto-configuration. Analyzer nên độc lập với application beans, không gọi network/database, không tự sửa cấu hình và trả null khi không nhận diện được lỗi. Reporter chịu trách nhiệm trình bày FailureAnalysis; phần lớn ứng dụng có thể dùng reporter mặc định.

Kiểm thử cần tách ba mục tiêu: unit test logic analyzer, context test để xác nhận exception thật được tạo, và integration/startup smoke test để xác nhận SpringApplication phát hiện analyzer từ artifact rồi báo Description/Action. Một thông báo tốt phải cụ thể, có thể hành động, đúng với điều analyzer biết và không làm lộ secret. Như vậy, khi ứng dụng không khởi động được, người vận hành có thể hiểu nguyên nhân và biết bước tiếp theo thay vì phải tự suy luận từ một stack trace dài.
## 20. Tạo thông báo cho lỗi bind cấu hình

Spring Boot có cơ chế binding các property vào @ConfigurationProperties. Khi giá trị không chuyển đổi được hoặc vi phạm validation, startup có thể thất bại với exception từ tầng binding/validation.

Ví dụ:

~~~java
package com.example.payment;

import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @NotNull Duration timeout,
        @Positive int maxAttempts) {
}
~~~

application.yml:

~~~yaml
app:
  payment:
    timeout: not-a-duration
    max-attempts: 3
~~~

Giá trị timeout không thể chuyển đổi thành Duration, nên quá trình binding có thể thất bại.

### 20.1. Ưu tiên validation rõ ràng trước khi viết analyzer

Nếu lỗi là một property không hợp lệ, thường nên:

- Dùng kiểu dữ liệu phù hợp trong @ConfigurationProperties.
- Dùng Jakarta Bean Validation như @NotBlank, @NotNull, @Positive, @Min, @Max khi thích hợp.
- Đặt thông báo validation rõ ràng.
- Cung cấp default hợp lý nếu property thật sự không bắt buộc.

Spring Boot đã có chẩn đoán cho nhiều lỗi binding. Chỉ thêm FailureAnalyzer khi cần biến lỗi kỹ thuật chung thành hướng dẫn thuộc domain/deployment.

### 20.2. Một analyzer domain có thể giải thích ý nghĩa của property

Ví dụ, property có mặt nhưng giá trị không được hệ thống hỗ trợ:

~~~text
Description:
The configured payment mode 'legacy-x' is not supported
by this version of the application.

Action:
Set 'app.payment.mode' to one of the supported values:
'sandbox' or 'live'. Confirm the selected mode with the
deployment configuration before restarting.
~~~

Thông báo này hữu ích hơn một lỗi chuyển đổi hoặc IllegalArgumentException nếu người vận hành cần biết các giá trị hợp lệ.

### 20.3. Không lặp lại toàn bộ giá trị cấu hình trong báo cáo

Nếu property chứa credential, URL có query token hoặc dữ liệu nhạy cảm, không in nguyên giá trị vào Description.

Có thể nói:

~~~text
The configured payment credential is invalid or unavailable.
~~~

và:

~~~text
Verify that the required secret is mounted and that the
service account can read it. Do not paste the secret into logs.
~~~

Analyzer nên hướng dẫn **cách kiểm tra an toàn**, không đưa secret vào log để thuận tiện chẩn đoán.

## 21. Xử lý lỗi thiếu bean và nhiều bean

Spring Boot có thể cung cấp FailureAnalysis cho một số tình huống dependency injection phổ biến.

### 21.1. Thiếu bean

Ví dụ:

~~~java
@Service
public class InvoiceService {

    private final TaxCalculator calculator;

    public InvoiceService(TaxCalculator calculator) {
        this.calculator = calculator;
    }
}
~~~

Nếu không có bean TaxCalculator phù hợp, context không thể tạo InvoiceService.

Thông báo hướng dẫn có thể chỉ ra:

- Type cần được đăng ký.
- Bean nào đang yêu cầu dependency đó.
- Cách khai báo @Component/@Bean hoặc thêm auto-configuration/dependency phù hợp.

### 21.2. Nhiều bean cùng type

~~~java
@Bean
TaxCalculator localTaxCalculator() {
    return new LocalTaxCalculator();
}

@Bean
TaxCalculator regionalTaxCalculator() {
    return new RegionalTaxCalculator();
}
~~~

Nếu một service inject TaxCalculator mà không có qualifier/primary và không có quy tắc lựa chọn phù hợp, Spring có thể không xác định được candidate duy nhất.

Action có thể hướng người dùng:

- Đánh dấu bean mặc định bằng @Primary nếu có một lựa chọn mặc định rõ ràng.
- Dùng @Qualifier tại injection point nếu cần chọn implementation cụ thể.
- Loại bỏ bean không cần thiết.

### 21.3. Không viết analyzer tổng quát cho mọi BeanCreationException

BeanCreationException có thể đại diện cho rất nhiều nguyên nhân:

- Constructor ném exception.
- Dependency không tồn tại.
- Property bind thất bại.
- File resource không đọc được.
- Lỗi kết nối external system.
- Lỗi khởi tạo thư viện bên thứ ba.

Một analyzer bắt mọi BeanCreationException và luôn nói “kiểm tra component scan” sẽ hướng dẫn sai nhiều trường hợp.

Hãy nhận diện cause cụ thể hoặc để analyzer mặc định của Boot xử lý.

## 22. Phân tích exception chain đúng cách

Một lỗi khởi động thường được wrap nhiều lần:

~~~text
ApplicationContextException
  └── BeanCreationException
       └── UnsatisfiedDependencyException
            └── IllegalStateException
                 └── MissingTenantConfigurationException
~~~

### 22.1. Không chỉ nhìn exception ngoài cùng

Exception ngoài cùng thường mô tả thất bại ở tầng framework. Root/cause bên trong có thể mang thông tin domain quan trọng hơn.

AbstractFailureAnalyzer giúp tìm cause theo generic type, tránh phải tự kiểm tra từng lớp wrapper.

### 22.2. Khi có nhiều cause cùng kiểu

Một chuỗi cause có thể chứa nhiều exception cùng type. AbstractFailureAnalyzer tìm một cause phù hợp theo cơ chế của nó; nếu thông điệp cần phân biệt các vị trí khác nhau, có thể:

- Dùng các exception subtype riêng.
- Bổ sung thông tin an toàn vào exception.
- Implement FailureAnalyzer trực tiếp với logic tìm cause có chủ đích.

Không nên parse stack trace string để xác định bean hoặc property.

### 22.3. Suppressed exceptions không nhất thiết là cause

Java có thể gắn suppressed exceptions khi close resource thất bại trong try-with-resources. Suppressed exception không nhất thiết nằm trên chuỗi getCause().

Nếu startup failure phụ thuộc vào lỗi cleanup, analyzer chỉ duyệt cause chain có thể không thấy suppressed exception. Hãy giữ exception gốc và sử dụng stack trace/diagnostic phù hợp; đừng mặc định mọi exception liên quan đều là cause trực tiếp.

## 23. Logging và FailureAnalysis

Khi startup thất bại, thông báo FailureAnalysis thường được gửi qua reporter mặc định và logging system. Tuy nhiên, analyzer không nên tự log toàn bộ lỗi rồi reporter lại log thêm lần nữa.

Ví dụ không nên:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    log.error("Tenant config failed", rootFailure);

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set app.tenant.id.",
            cause);
}
~~~

Điều này có thể tạo output trùng, đặc biệt khi startup framework cũng ghi exception/analysis.

Nên:

~~~java
@Override
protected FailureAnalysis analyze(
        Throwable rootFailure,
        MissingTenantConfigurationException cause) {

    return new FailureAnalysis(
            "Tenant configuration is missing.",
            "Set 'app.tenant.id' in the active configuration.",
            cause);
}
~~~

Để reporter chịu trách nhiệm trình bày. Nếu có nhu cầu log bổ sung, cần xác định rõ nơi ghi và tránh lặp stack trace.

### 23.1. Startup failure vẫn cần exit code khác 0

FailureAnalyzer không biến một startup failure thành startup success. Ứng dụng vẫn thất bại và launcher/orchestrator cần nhận biết process không khởi động được.

Trong CI/CD hoặc container orchestration:

- Process exit code cần được xử lý như thất bại.
- Không chỉ grep một dòng “APPLICATION FAILED TO START” rồi coi đó là toàn bộ trạng thái.
- Dùng health/readiness checks để quan sát trạng thái sau khi ứng dụng đã chạy.

### 23.2. FailureAnalysis không thay readiness/liveness probe

FailureAnalyzer xử lý **lỗi startup**. Kubernetes readiness/liveness probes và Actuator health endpoints phục vụ quan sát process/container trong thời gian chạy.

Không dùng analyzer để giải thích một pod đã khởi động nhưng về sau mất kết nối database. Trường hợp đó thuộc runtime monitoring, health checks và logging.

## 24. Hướng dẫn theo môi trường: local, test và production

Action nên phù hợp với môi trường đã biết, nhưng không nên đoán môi trường dựa trên tên hostname hoặc working directory.

### 24.1. Local development

Ví dụ:

~~~text
Action:
For a local run, add the following property to your
application-local.yml or pass it as a command-line argument:
--app.tenant.id=demo
~~~

Giá trị demo chỉ phù hợp nếu hệ thống local chấp nhận tenant giả lập.

### 24.2. Test

~~~text
Action:
Provide app.tenant.id in the test properties or test
configuration before starting the application context.
~~~

Không khuyến nghị dùng tenant production trong test chỉ để vượt qua startup validation.

### 24.3. Production

~~~text
Action:
Verify that the deployment supplies app.tenant.id through
the approved configuration source. Confirm the mounted
configuration/secret and restart the affected instance.
~~~

Không yêu cầu người vận hành sửa trực tiếp một file trong container nếu deployment quản lý file đó bằng ConfigMap, Secret hoặc hệ thống cấu hình trung tâm.

### 24.4. Không tự suy đoán active profile

Analyzer có thể đọc một exception nhưng không nhất thiết có Environment hoàn chỉnh. Đừng hard-code Action “edit application-prod.yml” chỉ vì ứng dụng thường chạy production.

Nếu analyzer thực sự được thiết kế để nhận Environment từ bootstrap một cách an toàn, phải có cơ chế cung cấp tường minh và test lifecycle. Còn trong thiết kế đơn giản, hãy hướng dẫn qua property key và nguồn cấu hình đang được deployment quản lý.

## 25. Thông báo lỗi và bảo mật

Startup error thường được ghi vào console, log collector, CI output và hệ thống giám sát. Một FailureAnalysis không phù hợp có thể làm lộ:

- Password hoặc token.
- Internal hostname, IP và topology.
- File path chứa tên người dùng hoặc thông tin nhạy cảm.
- Nội dung config nguyên bản.
- Request payload hoặc dữ liệu cá nhân.

### 25.1. Không đưa secret vào Description hoặc Action

Không:

~~~java
String action = "Use API key " + apiKey
        + " in your deployment environment.";
~~~

Nên:

~~~java
String action =
        "Verify that the required API key is available "
        + "from the approved secret source.";
~~~

### 25.2. Không ghi toàn bộ exception message nếu có dữ liệu nhạy cảm

Nếu custom exception được tạo từ input người dùng, message có thể chứa nội dung không an toàn. Analyzer nên tạo description từ **các trường đã kiểm soát**, thay vì nối trực tiếp exception.getMessage() trong mọi trường hợp.

### 25.3. Tránh thông báo quá chi tiết về hạ tầng nội bộ

Trong môi trường production, Action có thể nói:

~~~text
Verify the configured database endpoint and the service
account's access through the approved deployment tooling.
~~~

thay vì in mọi chi tiết connection string, subnet, username và credential.

Thông tin càng cụ thể càng hữu ích, nhưng chỉ nên hiển thị dữ liệu mà người đọc output được phép biết.

### 25.4. FailureAnalysis không phải nơi chứa remediation script tự động

Không nhúng script xóa file, kill process, sửa permission hoặc đổi production config vào Action với hàm ý người dùng nên chạy ngay mà chưa xác minh.

Action nên mô tả thao tác an toàn, có thể kiểm tra và phù hợp quyền của người vận hành.

