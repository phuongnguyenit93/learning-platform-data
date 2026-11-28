# Cấu hình WsConfigurer, API bị thay thế và khác biệt chữ ký mở rộng

> **Chương:** Nâng cấp và di chuyển
> **Phạm vi:** Spring Web Services (Spring-WS), đặc biệt là cấu hình SOAP server bằng Java Config và các điểm mở rộng khi nâng phiên bản thư viện.

## 1. Mục tiêu và tình huống áp dụng

Trong hệ thống SOAP phát triển theo hướng **contract-first**, XSD/WSDL là hợp đồng với đối tác; phía Java dùng JAXB, các endpoint, interceptor, SOAP Fault và cơ chế WS-Security để thực thi hợp đồng đó. Khi nâng cấp Spring Web Services, một thay đổi nhỏ tại lớp cấu hình có thể khiến chuỗi xác thực XML, kiểm tra chữ ký, ánh xạ tham số endpoint hoặc xử lý giá trị trả về không còn được đăng ký như trước, dù tài liệu WSDL không đổi.

Bài này giúp bạn:

1. Phân biệt vai trò của **WsConfigurer**, **WsConfigurerAdapter**, **DelegatingWsConfiguration** và **WsConfigurationSupport**.
2. Đọc đúng chữ ký ba callback cấu hình interceptor, argument resolver và return value handler.
3. Chuyển từ adapter cũ sang cách triển khai **WsConfigurer** phù hợp với Spring-WS 4.1 trở lên; biết điểm cần kiểm tra khi đi từ nhánh 4.x sang 5.x.
4. Xử lý các API bị đánh dấu deprecated/for removal mà không làm mất hành vi mặc định của framework.
5. Thiết kế kiểm thử hồi quy cho SOAP contract, fault, WS-Security và tương thích với client doanh nghiệp.

**Giới hạn:** WsConfigurer là điểm mở rộng của **SOAP server**, không phải cấu hình MVC controller hay SOAP client. Cấu hình WebServiceTemplate, ClientInterceptor, truststore và chứng chỉ phía client có vòng đời riêng; cần kiểm tra chúng trong kế hoạch nâng cấp tổng thể nhưng không đăng ký qua ba callback của WsConfigurer.

## 2. WsConfigurer nằm ở đâu trong luồng khởi tạo?

Khi một lớp cấu hình dùng **@EnableWs**, Spring nhập cấu hình nền qua **DelegatingWsConfiguration** (kế thừa **WsConfigurationSupport**). Lớp này thu thập các bean triển khai **WsConfigurer** rồi gọi callback để bổ sung các thành phần vào cấu hình SOAP endpoint.

~~~mermaid
flowchart TD
    A["@Configuration + @EnableWs"] --> B["DelegatingWsConfiguration"]
    C["Bean WsConfigurer: auditing"] --> B
    D["Bean WsConfigurer: validation"] --> B
    B --> E["WsConfigurationSupport"]
    E --> F["EndpointMapping + EndpointInterceptor"]
    E --> G["DefaultMethodEndpointAdapter"]
    G --> H["MethodArgumentResolver / MethodReturnValueHandler"]
    F --> I["SOAP endpoint"]
    H --> I
~~~

Ba callback thường dùng:

| Callback của WsConfigurer | Thay đổi được gì? | Tình huống cụ thể |
| --- | --- | --- |
| **addInterceptors(...)** | Bổ sung các **EndpointInterceptor** tham gia xử lý request/response SOAP của server. | Kiểm tra XSD, audit đã lọc dữ liệu nhạy cảm, xác thực WS-Security. |
| **addArgumentResolvers(...)** | Bổ sung **MethodArgumentResolver** chuyển đầu vào thành tham số của phương thức endpoint. | Trích xuất một kiểu dữ liệu tùy chỉnh từ SOAP message/header. |
| **addReturnValueHandlers(...)** | Bổ sung **MethodReturnValueHandler** xử lý kiểu trả về của phương thức endpoint. | Ghi một kiểu kết quả đặc thù thành nội dung SOAP response. |

Các callback tùy chỉnh **hành vi server**, không tự sinh WSDL, không chỉnh XSD và cũng không tự tạo chính sách bảo mật. Định nghĩa schema/WSDL, JAXB, endpoint mapping và WS-Security cần được giữ đồng bộ bằng kiểm thử.

## 3. Khác biệt giữa các nhánh phiên bản

Đọc đúng **phiên bản Spring-WS thực tế trong dependency tree** trước khi sửa source. Một chữ ký giống nhau về tên có thể khác trạng thái API giữa các bản phát hành.

| Nhánh | WsConfigurer | WsConfigurerAdapter | Hệ quả khi di chuyển |
| --- | --- | --- | --- |
| **4.0.x** | Ba phương thức callback là **abstract** trong interface. | Có thể kế thừa adapter với các phương thức rỗng để chỉ override phần cần dùng. | Nếu đổi trực tiếp sang implements WsConfigurer trên 4.0.x, phải triển khai đủ ba phương thức. |
| **4.1.x** | Ba phương thức trở thành **default methods**; triển khai trực tiếp và chỉ override phần cần dùng. | Được đánh dấu **@Deprecated(since = "4.1.0", forRemoval = true)**. | Ưu tiên implements WsConfigurer, bỏ kế thừa adapter và các lệnh gọi super rỗng. |
| **5.0.x** | Tiếp tục dùng trực tiếp **WsConfigurer** với các callback default. | Không nên phụ thuộc vào adapter cũ; kiểm tra API của đúng phiên bản đích khi biên dịch. | Đồng thời đánh giá thay đổi nền tảng Spring Framework 7, Jakarta EE 11 và null safety. |
| **5.1.x** | Mẫu cấu hình trực tiếp qua interface vẫn là hướng phù hợp. | Dòng 5.1 có đợt loại bỏ API cũ đã đánh dấu for removal. | Quét mã dùng API cũ và biên dịch với artifact đích; kiểm tra thêm các thay đổi về bảo mật/quan sát hệ thống. |

Lưu ý về nền tảng: Spring-WS **4.0** gắn với Spring Framework 6, Java 17 và chuyển nhiều API Java EE từ **javax.*** sang **jakarta.***; Spring-WS **5.0** chuyển sang Spring Framework 7, Jakarta EE 11 và sử dụng JSpecify cho null safety. Việc đổi package Jakarta chỉ áp dụng cho các API tương ứng (ví dụ Servlet/JAXB), **không** đổi tên package **org.springframework.ws.***.

Đến tháng 11/2026, Spring-WS 5.1.0 đã được công bố. Trong dự án thực tế, hãy dùng release notes và Javadoc đúng bản vá được khóa trong Maven/Gradle; tránh suy trạng thái deprecated từ đường dẫn tài liệu “current” vì đường dẫn này có thể trỏ tới một nhánh khác.

## 4. Chữ ký mở rộng phải chính xác tuyệt đối

Với Spring-WS **4.1+**, interface có dạng tương đương sau (rút gọn từ API công khai):

~~~java
package org.springframework.ws.config.annotation;

public interface WsConfigurer {
    default void addInterceptors(
            java.util.List<org.springframework.ws.server.EndpointInterceptor> interceptors) {
    }

    default void addArgumentResolvers(
            java.util.List<org.springframework.ws.server.endpoint.adapter.method.MethodArgumentResolver> resolvers) {
    }

    default void addReturnValueHandlers(
            java.util.List<org.springframework.ws.server.endpoint.adapter.method.MethodReturnValueHandler> handlers) {
    }
}
~~~

**Đây là sơ đồ chữ ký để học, không phải mã cần chép đè vào thư viện.** Khi override callback thực tế, khai báo **public void** và giữ nguyên kiểu phần tử của **List**:

~~~java
import java.util.List;

import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.adapter.method.MethodArgumentResolver;
import org.springframework.ws.server.endpoint.adapter.method.MethodReturnValueHandler;

public class SoapExtensions implements WsConfigurer {

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        // Thêm interceptor SOAP server nếu cần.
    }

    @Override
    public void addArgumentResolvers(List<MethodArgumentResolver> resolvers) {
        // Thêm resolver của Spring-WS nếu cần.
    }

    @Override
    public void addReturnValueHandlers(List<MethodReturnValueHandler> handlers) {
        // Thêm handler của Spring-WS nếu cần.
    }
}
~~~

Ở Spring-WS 4.1+, có thể xóa các callback rỗng và chỉ giữ callback thực sự sử dụng. Nếu vẫn chạy 4.0.x, việc xóa hai callback rỗng khiến class triển khai interface không biên dịch, vì ba phương thức khi đó còn abstract.

### Hai họ API dễ bị nhập nhằng

- **Spring-WS:** org.springframework.ws.server.EndpointInterceptor và org.springframework.ws.server.endpoint.adapter.method.MethodArgumentResolver / MethodReturnValueHandler.
- **Spring MVC:** org.springframework.web.servlet.HandlerInterceptor và org.springframework.web.method.support.HandlerMethodArgumentResolver / HandlerMethodReturnValueHandler.

Chúng phục vụ hai pipeline khác nhau. Việc IDE tự import một tên gần giống khiến **@Override không khớp**, hoặc xuất hiện lỗi **name clash** do generic type erasure. Luôn giữ annotation **@Override** để trình biên dịch phát hiện ngay. Tên biến tham số có thể đổi; **tên phương thức, số lượng và kiểu tham số, visibility** mới quyết định chữ ký.

**Phân biệt access modifier:** ở interface WsConfigurer, phương thức override phải là **public**; còn các hook cùng tên trong **WsConfigurationSupport** có thể là **protected** vì chúng là template method của lớp cha. Không sao chép nguyên xi **protected void** từ ví dụ subclass sang class implements WsConfigurer.

## 5. Thay thế WsConfigurerAdapter từng bước

### 5.1. Mã cũ: kế thừa adapter

Một cấu hình quen thuộc ở 4.0.x:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurerAdapter;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.interceptor.PayloadLoggingInterceptor;

@Configuration
@EnableWs
public class LegacySoapConfig extends WsConfigurerAdapter {

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(new PayloadLoggingInterceptor());
    }
}
~~~

Trong 4.1.x, class adapter bị đánh dấu **deprecated for removal**. Để tránh ràng buộc với API sắp bị loại bỏ, viết lại như sau.

### 5.2. Mã mới: implements WsConfigurer

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.interceptor.PayloadLoggingInterceptor;

@Configuration
@EnableWs
public class SoapConfig implements WsConfigurer {

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(new PayloadLoggingInterceptor());
    }
}
~~~

Mã mới chỉ cần override một callback khi dùng Spring-WS 4.1+. **PayloadLoggingInterceptor ở đây chỉ dùng để minh họa đăng ký hook**: không bật logging payload chứa mật khẩu, token, chữ ký, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm trong môi trường thực.

Những chỉnh sửa tối thiểu khi chuyển đổi:

1. Thay **extends WsConfigurerAdapter** bằng **implements WsConfigurer**.
2. Đổi import sang **org.springframework.ws.config.annotation.WsConfigurer**; giữ import **EndpointInterceptor** thuộc Spring-WS.
3. Xóa lệnh gọi **super.addInterceptors(...)**, **super.addArgumentResolvers(...)**, **super.addReturnValueHandlers(...)** của adapter rỗng.
4. Dùng **public void** với đúng kiểu **List**; nếu thiếu **@Override** trước đó, bổ sung để bắt lỗi chữ ký.
5. Trên Spring-WS 4.1+ có thể bỏ method rỗng; với Spring-WS 4.0.x phải giữ đủ callback hoặc tạm dùng adapter.
6. Khởi động lại context, kiểm tra callback được gọi và interceptor thực sự nằm trong chuỗi của endpoint mapping.

### 5.3. Ví dụ contract-first thực tế: kiểm tra XSD trước endpoint

Giả sử hệ thống cung cấp SOAP operation **submitOrder**, contract ở **src/main/resources/xsd/orders.xsd**, JAXB ánh xạ request/response từ schema và endpoint xử lý đặt hàng. Một cách tổ chức dễ kiểm soát là tạo bean schema và interceptor riêng, rồi đưa interceptor vào cấu hình server.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

import java.util.List;

@Configuration
class OrderSchemaConfig {

    @Bean("ordersSchema")
    XsdSchema ordersSchema() {
        return new SimpleXsdSchema(new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean("ordersValidator")
    PayloadValidatingInterceptor ordersValidator(
            @Qualifier("ordersSchema") XsdSchema schema) {

        PayloadValidatingInterceptor validator = new PayloadValidatingInterceptor();
        validator.setXsdSchema(schema);
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);
        return validator;
    }
}

@Configuration
@EnableWs
class OrderSoapConfig implements WsConfigurer {
    private final PayloadValidatingInterceptor validator;

    OrderSoapConfig(
            @Qualifier("ordersValidator") PayloadValidatingInterceptor validator) {
        this.validator = validator;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(validator);
    }
}
~~~

Giả định: hai lớp nằm trong phạm vi component scan của ứng dụng, thư viện Spring-WS tương thích đã được khai báo, và file XSD tồn tại ở đường dẫn trên. Với cấu hình này, cấu trúc XML sai schema có thể bị chặn trước khi endpoint thực thi. Nếu request/response có khác biệt schema có chủ đích, cần áp dụng chiến lược versioning hoặc validation tương ứng thay vì tắt validation để “cho qua” lỗi.

Trong hệ thống có **Wss4jSecurityInterceptor**, thứ tự kiểm tra chữ ký, giải mã và xác thực XSD ảnh hưởng kết quả. Thiết lập chuỗi interceptor trong một cấu hình có thứ tự rõ ràng, chạy các tình huống message đã ký/mã hóa, message sai chữ ký, và SOAP Fault. Không kết luận dữ liệu đã an toàn chỉ vì interceptor được khởi tạo: phải chứng minh bằng request thực tế và kiểm thử.

## 6. Nhiều cấu hình WsConfigurer trong cùng ứng dụng

**@EnableWs** chỉ nên đặt trên **một** lớp **@Configuration** trong cùng application context để nhập hạ tầng Spring-WS. Ngược lại, có thể có **nhiều bean WsConfigurer**:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.interceptor.PayloadLoggingInterceptor;

@Configuration
@EnableWs
class EnableSoapServer {
}

@Configuration
class SoapLoggingConfiguration implements WsConfigurer {
    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(new PayloadLoggingInterceptor());
    }
}
~~~

**Đoạn trên minh họa hai lớp cấu hình cùng phối hợp**, trong đó logging payload chỉ phù hợp với dữ liệu thử nghiệm đã được kiểm soát. DelegatingWsConfiguration thu thập các bean triển khai WsConfigurer để áp dụng callback; không cần tự lập một **WsConfigurerComposite**. Với chuỗi mà **thứ tự có ý nghĩa bảo mật**, nên quản lý việc thêm các interceptor trong một configurer và kiểm thử thứ tự thực tế, thay vì giả định thứ tự quét bean luôn ổn định.

Nếu cả ứng dụng có SOAP và REST, việc triển khai **WebMvcConfigurer** không thay thế được **WsConfigurer**. Chúng cấu hình các phần khác nhau của ứng dụng.

## 7. API bị thay thế và cách đọc hướng di chuyển

Ngoài WsConfigurerAdapter, một số API trong quá trình nâng cấp thường xuất hiện cảnh báo:

| API cũ hoặc dấu hiệu | Trạng thái/ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| **WsConfigurerAdapter** | Deprecated for removal từ **4.1.0**. | Dùng **implements WsConfigurer**; trên 4.1+ chỉ override callback cần thiết. |
| **WsConfigurerComposite** | Deprecated for removal từ **4.0.12**, tài liệu ghi **không có replacement trực tiếp**. | Để **DelegatingWsConfiguration** thu thập các bean WsConfigurer hoặc tự quản lý chuỗi callback khi có yêu cầu đặc biệt. |
| **DelegatingWsConfiguration.setConfigurers(List&lt;WsConfigurer&gt;)** | Overload nhận List bị đánh dấu deprecated for removal. | Thông thường không gọi thủ công; để Spring tự phát hiện WsConfigurer. Nếu đang tùy biến hạ tầng, kiểm tra overload và API trên đúng phiên bản. |
| **DefaultMethodEndpointAdapter.setCustomMethodArgumentResolvers(...)** | Deprecated từ **4.1.0**, chuyển dần sang mô hình một danh sách resolver. | Ưu tiên **WsConfigurer.addArgumentResolvers(...)**; khi cấu hình adapter trực tiếp thì xem **setMethodArgumentResolvers(...)** và giữ các resolver mặc định cần thiết. |
| **DefaultMethodEndpointAdapter.setCustomMethodReturnValueHandlers(...)** | Deprecated từ **4.1.0**. | Ưu tiên **WsConfigurer.addReturnValueHandlers(...)**; khi chỉnh adapter trực tiếp thì xem **setMethodReturnValueHandlers(...)**. |
| **getCustomMethodArgumentResolvers() / getCustomMethodReturnValueHandlers()** | Deprecated từ **4.1.0**, Javadoc ghi không có replacement tương đương trực tiếp. | Đánh giá lại mục đích đọc “custom”; danh sách hợp nhất **getMethodArgumentResolvers() / getMethodReturnValueHandlers()** không phải luôn đồng nghĩa danh sách chỉ gồm phần mở rộng. |

**Bẫy quan trọng:** ở đường đi cấu hình trực tiếp **DefaultMethodEndpointAdapter**, việc gọi setter thay thế với danh sách **chỉ chứa custom resolver** có thể làm mất các resolver mặc định cho JAXB, DOM hoặc các kiểu argument đã hỗ trợ. Nếu muốn bổ sung chứ không thay thế, dùng callback **addArgumentResolvers** / **addReturnValueHandlers** của WsConfigurer; nếu buộc phải cấu hình adapter, cần xác định rõ danh sách mặc định và thứ tự áp dụng trong phiên bản đang chạy.

Phân biệt các nhãn trong Javadoc:

- **@Deprecated**: API còn có thể biên dịch ở phiên bản hiện tại nhưng dự kiến không còn được ưu tiên.
- **forRemoval = true**: có kế hoạch gỡ bỏ trong một phiên bản tương lai; **không có nghĩa đã bị gỡ ngay** tại bản đầu tiên gắn nhãn.
- **Removed/không tìm thấy symbol**: phải thay đường gọi hoặc cách cấu hình. Đừng chỉ tắt compiler warning.

Trong một đợt nâng cấp, phạm vi có thể lan tới Spring Boot, Spring Framework, servlet, JAXB, HTTP transport, WSS4J và Spring Security. Tách rõ lỗi cấu hình **WsConfigurer** với lỗi dependency hoặc namespace để xử lý đúng nguyên nhân.

## 8. Khi nào cần WsConfigurationSupport thay cho WsConfigurer?

**WsConfigurer** chỉ cung cấp ba callback đã nêu. Nếu cần thay đổi sâu hơn như tạo lại **PayloadRootAnnotationMethodEndpointMapping** hoặc **DefaultMethodEndpointAdapter** với cấu hình đặc biệt, tài liệu Spring-WS chỉ dẫn tùy biến bằng lớp kế thừa **WsConfigurationSupport**.

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.WsConfigurationSupport;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.server.endpoint.interceptor.PayloadLoggingInterceptor;

@Configuration
public class AdvancedSoapConfiguration extends WsConfigurationSupport {

    @Override
    protected void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(new PayloadLoggingInterceptor());
    }
}
~~~

Ở kiểu **kế thừa WsConfigurationSupport**, hook có access modifier **protected**; lớp cấu hình này **không đồng thời đặt @EnableWs** vì annotation sẽ nhập thêm DelegatingWsConfiguration và dễ khiến cấu hình hạ tầng chồng lấn. Khi override phương thức tạo bean vốn mang **@Bean** từ lớp cha, phải xem lại annotation **@Bean** trên phương thức override theo hướng dẫn Javadoc và kiểm tra lifecycle bean thực tế.

Chỉ nên đi đường này khi callback của WsConfigurer thực sự không đủ. Việc thay hẳn adapter hoặc mapping có thể tác động cách tìm **@PayloadRoot**, **@SoapAction**, argument resolver, SOAP Fault và những endpoint cũ; chi phí kiểm thử cao hơn nhiều so với thêm interceptor qua interface.

## 9. Những lỗi chữ ký thường gặp khi nâng cấp

| Biểu hiện | Nguyên nhân thường gặp | Cách phát hiện/sửa |
| --- | --- | --- |
| **method does not override or implement a method from a supertype** | Import nhầm **org.springframework.web.servlet.HandlerInterceptor** hoặc resolver của MVC. | Kiểm tra fully qualified class và **@Override**. |
| **attempting to assign weaker access privileges** | Ghi **protected** khi triển khai interface WsConfigurer. | Dùng **public void**. |
| **class is not abstract and does not override ...** trên Spring-WS 4.0 | Interface còn ba method abstract. | Triển khai đủ cả ba hoặc tạm kế thừa adapter nếu chưa nâng phiên bản. |
| **cannot find symbol: WsConfigurerAdapter** | Đã chọn artifact không còn cung cấp lớp adapter. | Dùng **implements WsConfigurer**; loại bỏ import và super calls. |
| **name clash: same erasure** | Danh sách tham số generic dùng sai kiểu interceptor/resolver, ví dụ MVC thay cho Spring-WS. | Sửa import, method declaration, không tạo overload “chữa cháy”. |
| Context lên nhưng SOAP request không qua validator | Cấu hình không được phát hiện, thiếu @EnableWs ở nơi cần thiết, hoặc mapping tùy chỉnh không gắn interceptor. | Kiểm tra bean/configuration và chạy request lỗi schema để xác minh interceptor thật sự xử lý. |
| Payload JAXB đang chạy bỗng không ánh xạ được | Ghi đè danh sách resolver/handler mặc định trên DefaultMethodEndpointAdapter. | Bổ sung bằng WsConfigurer hoặc tạo lại danh sách đầy đủ. |
| SOAP Fault/WS-Security đổi hành vi | Sai thứ tự interceptor, thiếu handler sau khi refactor, thư viện security thay đổi. | Kiểm thử cả luồng thành công và nhánh lỗi, bao gồm chữ ký/chứng chỉ. |

Ví dụ lỗi do import nhầm:

~~~java
// SAI: HandlerInterceptor của Spring MVC, không phải SOAP EndpointInterceptor.
import org.springframework.web.servlet.HandlerInterceptor;

// @Override dưới đây không khớp WsConfigurer.addInterceptors.
public void addInterceptors(List<HandlerInterceptor> interceptors) {
}
~~~

~~~java
// ĐÚNG: dùng Spring-WS endpoint interceptor.
import org.springframework.ws.server.EndpointInterceptor;

@Override
public void addInterceptors(List<EndpointInterceptor> interceptors) {
}
~~~

## 10. Quy trình di chuyển an toàn trong dự án doanh nghiệp

Giả sử đang chuyển một dịch vụ SOAP nhận đơn hàng từ Spring-WS 4.0/4.1 sang 5.x. Bạn có thể triển khai theo các cổng kiểm tra sau.

### Giai đoạn A — Chụp hành vi trước nâng cấp

1. Khóa phiên bản JDK, Spring Boot/Spring Framework và Spring-WS hiện tại; xuất dependency tree để tìm mọi artifact Spring-WS, Spring XML, JAXB, Jakarta và WSS4J.
2. Lưu bản WSDL/XSD đã công bố; lưu mẫu SOAP request/response và Fault từ đối tác. Ghi nhận namespace, QName, SOAPAction, header WS-Security và certificate chain.
3. Liệt kê mọi chỗ kế thừa WsConfigurerAdapter, tự lắp WsConfigurerComposite, override WsConfigurationSupport hoặc cấu hình thủ công DefaultMethodEndpointAdapter.
4. Kiểm thử baseline: endpoint mapping, JAXB marshal/unmarshal, kiểm tra schema, SOAP Fault, client WebServiceTemplate và negative cases bảo mật.

### Giai đoạn B — Sửa mã nguồn và cấu hình

1. Chọn phiên bản đích đồng bộ với Spring Framework/Boot; chuyển các import **javax → jakarta** nơi thư viện nền tảng yêu cầu.
2. Đổi **extends WsConfigurerAdapter → implements WsConfigurer**; kiểm tra ba chữ ký, callback rỗng và thứ tự interceptor.
3. Với API deprecated khác, đọc Javadoc của bản đích; không tự giả định setter/getter mới tương đương 1:1 với API cũ.
4. Xác nhận chỉ một nơi enable SOAP; các cấu hình WsConfigurer khác vẫn được tạo bean và phát hiện.
5. Giữ nguyên contract XSD/WSDL nếu mục tiêu chỉ là nâng cấp hạ tầng. Nếu cần đổi contract, quản lý versioning và đánh giá tác động với client riêng.

### Giai đoạn C — Kiểm chứng bằng hành vi

| Bài kiểm thử | Đầu vào | Kết quả cần quan sát |
| --- | --- | --- |
| SOAP hợp lệ | XML đúng namespace/XSD, operation tồn tại. | Endpoint được gọi, JAXB ánh xạ đúng, response hợp đồng không đổi. |
| SOAP sai schema | Thiếu field bắt buộc, sai kiểu, sai namespace. | Interceptor validation thực sự chạy và trả lỗi dự kiến; không xử lý nghiệp vụ ngoài ý muốn. |
| SOAP operation lạ | QName hoặc SOAPAction không khớp. | Endpoint mapping và Fault theo chính sách dự kiến. |
| SOAP Fault nghiệp vụ | Endpoint ném exception đã ánh xạ. | Fault code/string/detail đúng yêu cầu tích hợp, không rò stack trace nhạy cảm. |
| WS-Security hợp lệ | SOAP có chữ ký/token/chứng chỉ đúng. | Xác thực thành công, thứ tự kiểm tra bảo mật hoạt động. |
| WS-Security không hợp lệ | Chữ ký sai, token hết hạn, chứng chỉ không tin cậy. | Request bị từ chối; endpoint không được xử lý trái phép. |
| Hồi quy client | Client cũ gọi WSDL/endpoint như trước. | Không đổi ngoài ý muốn ở SOAP envelope, header, encoding, action và Fault. |
| Bootstrap context | Khởi động toàn ứng dụng với cấu hình mới. | Không lỗi bean trùng, không mất resolver/handler, callback chạy đúng. |

Có thể dùng **MockWebServiceClient** để kiểm tra request/response ở server và **MockWebServiceServer** để kiểm tra SOAP client. Với các tình huống WS-Security, chứng chỉ, TLS hoặc hệ thống tích hợp ngoài, bổ sung integration test chạy qua transport thật. Mock endpoint thành công chưa chứng minh cấu hình bảo mật end-to-end đã đúng.

### Giai đoạn D — Triển khai có kiểm soát

Giữ bản ghi kiểm thử trước/sau, diff WSDL/XSD, đánh giá log/metric và thử gọi với ít nhất một client thực tế. Kiểm tra cảnh báo deprecated còn tồn tại; xử lý theo phiên bản đích và ưu tiên các API **forRemoval=true**. Khi có thay đổi WS-Security hoặc chứng chỉ, phối hợp lịch quay vòng khóa và khả năng trust đối tác thay vì giả định client sẽ tự tương thích.

## 11. Tình huống thực hành

**Bối cảnh:** Dịch vụ **submitOrder** dùng schema XSD cố định, code cũ kế thừa WsConfigurerAdapter để thêm validator và WSS4J interceptor. Sau nâng cấp, IDE báo không tìm thấy adapter; một lập trình viên đổi sang WsConfigurer nhưng copy **protected void addInterceptors(...)** từ ví dụ WsConfigurationSupport.

**Yêu cầu:**

1. Tìm hai lỗi độc lập: class adapter không còn phù hợp với artifact đích; method interface override phải là **public**, không phải protected.
2. Chuyển cấu hình sang **implements WsConfigurer** và **public void addInterceptors(List&lt;EndpointInterceptor&gt;)**.
3. Đảm bảo danh sách interceptor chứa cả validation và security theo đúng thứ tự được xác minh qua test; không xóa callback resolver/handler của ứng dụng nếu chúng đang thực hiện chuyển đổi đặc thù.
4. Kiểm thử hai SOAP request: một message hợp lệ đã ký, một message sai chữ ký nhưng đúng XSD. Lần thứ hai phải bị từ chối trước khi logic submitOrder chạy.
5. So sánh WSDL trước/sau nâng cấp và chạy lại client cũ để phát hiện thay đổi contract hoặc Fault.

**Tiêu chí đạt:** source biên dịch với dependency đích; context nạp không trùng; các callback được áp dụng; các bài thử tích hợp thành công; không bỏ lọt request sai XSD/chữ ký. Việc biên dịch thành công **chưa đủ** chứng minh đã di chuyển chính xác.

## 12. Ghi nhớ và tài liệu đối chiếu

- **WsConfigurer** là điểm mở rộng Java Config của **SOAP server**. Dùng **@Override** và các kiểu thuộc **org.springframework.ws.***.
- Spring-WS **4.0.x**: ba callback interface còn abstract. **4.1+**: callback là default và **WsConfigurerAdapter** deprecated for removal.
- **WsConfigurationSupport** là đường tùy biến hạ tầng sâu hơn; hook có thể **protected**, khác với **public** trong interface.
- Tránh thay một danh sách resolver/handler mặc định bằng danh sách chỉ có custom handler. Đọc kỹ API khi chuyển từ **setCustom...**.
- Bảo toàn hành vi contract-first qua các phép thử XSD/WSDL, JAXB, endpoint mapping, Fault, WS-Security, chứng chỉ và client tương thích.

Nguồn tham chiếu chính thức để tra cứu theo phiên bản:

1. [Spring-WS 4.0.x — WsConfigurer Javadoc](https://docs.spring.io/spring-ws/docs/4.0.x/api/org/springframework/ws/config/annotation/WsConfigurer.html).
2. [Spring-WS 4.1.1 — WsConfigurer Javadoc](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/config/annotation/WsConfigurer.html).
3. [Spring-WS 4.1.1 — @EnableWs Javadoc](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/config/annotation/EnableWs.html).
4. [Spring-WS 4.1.1 — Deprecated API](https://docs.spring.io/spring-ws/docs/4.1.1/api/deprecated-list.html).
5. [Spring-WS 4.1.1 — DefaultMethodEndpointAdapter Javadoc](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/server/endpoint/adapter/DefaultMethodEndpointAdapter.html).
6. [Spring-WS 4.0.x — WsConfigurationSupport Javadoc](https://docs.spring.io/spring-ws/docs/4.0.x/api/org/springframework/ws/config/annotation/WsConfigurationSupport.html).
7. [Spring-WS 5.0.0 — thông báo phát hành](https://spring.io/blog/2025/11/18/spring-ws-5-0-0-available-now/).
8. [Spring-WS 5.1.0 — thông báo phát hành](https://spring.io/blog/2026/11/19/spring-ws-5-1-0-available-now/).
