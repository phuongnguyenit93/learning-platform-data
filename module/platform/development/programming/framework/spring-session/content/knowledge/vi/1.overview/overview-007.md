# Phiên phân tán, sticky session và nhân bản container

Khi một ứng dụng Spring chạy trên một máy chủ, servlet container thường giữ dữ liệu phiên (HTTP session) trong bộ nhớ của tiến trình đó. Cách làm này đơn giản, nhưng trở thành vấn đề khi triển khai nhiều bản sao ứng dụng: bộ cân bằng tải có thể gửi hai yêu cầu liên tiếp của cùng một người dùng đến hai máy chủ khác nhau. Máy chủ thứ hai không có phiên được tạo ở máy chủ thứ nhất, nên người dùng có thể bị xem như chưa đăng nhập hoặc mất trạng thái giỏ hàng.

Spring Session giải quyết vấn đề bằng cách tách việc lưu trữ phiên khỏi bộ nhớ riêng của từng servlet container. Các bản sao ứng dụng có thể đọc và cập nhật cùng một phiên thông qua kho dữ liệu dùng chung như Redis hoặc JDBC. Sticky session và cơ chế nhân bản phiên của servlet container là những cách tiếp cận khác nhau; hiểu rõ sự khác nhau giúp chọn kiến trúc phù hợp khi mở rộng ứng dụng.

## 1. Vì sao phiên trong bộ nhớ cục bộ gặp vấn đề?

HTTP không tự ghi nhớ trạng thái giữa các yêu cầu. Ứng dụng thường dùng HTTP session để lưu những thông tin cần tồn tại qua nhiều yêu cầu, chẳng hạn mã người dùng đã đăng nhập, mã giỏ hàng hoặc một số lựa chọn tạm thời. Trình duyệt gửi cookie chứa mã phiên trong các yêu cầu tiếp theo. Máy chủ dùng mã đó để tìm dữ liệu phiên tương ứng.

Trong cấu hình mặc định của nhiều servlet container, dữ liệu phiên được giữ trong bộ nhớ của chính tiến trình ứng dụng. Ví dụ, hai bản sao của cùng một ứng dụng có thể có trạng thái như sau:

| Bản sao ứng dụng | Phiên đang có trong bộ nhớ |
| --- | --- |
| Instance A | Phiên S1 của trình duyệt |
| Instance B | Không có phiên S1 |

Giả sử yêu cầu đăng nhập được gửi đến Instance A. A tạo phiên S1 và trả cookie chứa mã phiên về trình duyệt. Yêu cầu tiếp theo được bộ cân bằng tải chuyển đến Instance B. B nhận được mã S1 nhưng không tìm thấy dữ liệu tương ứng trong bộ nhớ của mình. Từ góc nhìn của B, phiên không tồn tại hoặc đã hết hạn.

Đây là vấn đề về vị trí lưu trạng thái. Tăng số lượng bản sao ứng dụng không tự động làm cho bộ nhớ của chúng được chia sẻ.

## 2. Phiên phân tán với Spring Session

Phiên phân tán là phiên có dữ liệu được lưu ở một kho mà nhiều bản sao ứng dụng cùng truy cập được. Spring Session cung cấp lớp trừu tượng để ứng dụng tiếp tục làm việc với API quen thuộc như HttpSession, trong khi dữ liệu phiên được lưu bằng một SessionRepository.

Với Spring Session, SessionRepositoryFilter tích hợp vào chuỗi xử lý Servlet và cung cấp đối tượng HttpSession được quản lý bởi Spring Session. Khi ứng dụng đọc hoặc thay đổi thuộc tính phiên, Spring Session làm việc với repository đã cấu hình. Repository có thể lưu phiên vào Redis hoặc cơ sở dữ liệu quan hệ thông qua JDBC.

Cookie gửi về trình duyệt chỉ mang mã nhận diện phiên. Dữ liệu phiên thực tế được giữ ở kho dùng chung, không được nhúng toàn bộ vào cookie. Vì vậy, mọi instance có thể nhận cùng mã phiên và truy xuất cùng dữ liệu:

~~~mermaid
flowchart TD
    B["Trình duyệt<br/>Cookie chứa session ID"] --> LB["Load balancer"]
    LB --> A["Instance A<br/>Spring Session"]
    LB --> C["Instance B<br/>Spring Session"]
    A --> F["SessionRepositoryFilter"]
    C --> G["SessionRepositoryFilter"]
    F --> R[("Kho phiên dùng chung<br/>Redis hoặc JDBC")]
    G --> R
~~~

Luồng xử lý cơ bản:

1. Trình duyệt gửi yêu cầu cùng cookie chứa session ID.
2. Load balancer chọn một instance đang hoạt động.
3. Spring Session trên instance đó đọc session ID và yêu cầu repository tải dữ liệu phiên từ kho dùng chung.
4. Controller hoặc service sử dụng HttpSession như bình thường.
5. Khi phiên được cập nhật, Spring Session lưu thay đổi vào repository theo chế độ lưu đã cấu hình.
6. Phản hồi được gửi về trình duyệt. Cookie phiên tiếp tục được sử dụng cho các yêu cầu sau.

Nếu yêu cầu kế tiếp đến một instance khác, instance đó cũng đọc cùng kho dữ liệu và có thể khôi phục phiên. Tính liên tục của phiên vì thế không còn phụ thuộc vào việc yêu cầu được gửi đến đúng máy chủ đã tạo phiên.

### Lợi ích và điều kiện cần

- Các instance có thể mở rộng hoặc thay thế độc lập mà vẫn truy cập được phiên đang tồn tại.
- Khi một instance dừng hoặc được triển khai phiên bản mới, phiên không mất chỉ vì bộ nhớ cục bộ của instance đó bị giải phóng.
- Load balancer có thể phân phối yêu cầu đến bất kỳ instance phù hợp nào mà không cần giữ người dùng ở một máy chủ cố định.
- Kho phiên trở thành một thành phần quan trọng của hệ thống. Nó cần được bảo vệ, giám sát, sao lưu hoặc triển khai tính sẵn sàng cao tùy theo yêu cầu vận hành.

Các instance phải dùng cùng kho dữ liệu, cùng namespace của ứng dụng và cấu hình tương thích. Nếu hai instance kết nối đến hai Redis khác nhau hoặc dùng namespace khác nhau, chúng vẫn không nhìn thấy cùng một phiên.

## 3. Sticky session là gì?

Sticky session, còn gọi là session affinity hoặc định tuyến bám phiên, là cơ chế của load balancer nhằm đưa các yêu cầu tiếp theo của một người dùng hoặc một phiên về cùng một backend. Load balancer có thể dùng cookie do nó phát hành, cookie của ứng dụng hoặc một quy tắc affinity khác để nhận biết backend cần chọn.

Ví dụ, khi yêu cầu đầu tiên được gửi đến Instance A, load balancer ghi nhận ánh xạ người dùng với A. Những yêu cầu sau được ưu tiên chuyển về A:

~~~mermaid
flowchart TD
    B["Trình duyệt"] --> LB["Load balancer<br/>Affinity"]
    LB --> A["Instance A<br/>Giữ phiên trong bộ nhớ"]
    LB -. "Yêu cầu khác" .-> C["Instance B"]
    A --> S["Session S1 trong bộ nhớ A"]
~~~

Sticky session có thể hữu ích khi ứng dụng còn lưu trạng thái cục bộ, hoặc khi muốn tăng khả năng tái sử dụng dữ liệu đã được nạp trong bộ nhớ của một instance. Tuy nhiên, affinity chỉ ảnh hưởng đến định tuyến; nó không sao chép dữ liệu phiên sang các instance khác.

### Giới hạn của sticky session

- Nếu instance đang giữ phiên bị lỗi, bị thay thế hoặc bị loại khỏi cụm, phiên trong bộ nhớ của nó có thể mất. Yêu cầu tiếp theo được chuyển sang instance khác sẽ không tìm thấy phiên.
- Một backend có thể nhận quá nhiều yêu cầu nếu nhiều người dùng bị ghim vào cùng máy chủ, làm tải phân bố không đều.
- Việc triển khai, thay đổi hoặc mở rộng cụm cần xử lý lại ánh xạ affinity. Không phải mọi thay đổi hạ tầng đều giữ được ánh xạ cũ.
- Một số cách affinity dựa trên địa chỉ IP có thể phân phối kém chính xác khi nhiều người dùng đi qua cùng proxy hoặc NAT.
- Sticky session không thay thế cho việc quản lý phiên dùng chung nếu yêu cầu đặt ra là chịu lỗi và mở rộng ngang.

### Sticky session và phiên phân tán có thể kết hợp

Khi dùng Spring Session với Redis hoặc JDBC, sticky session không còn là điều kiện để tìm đúng phiên. Bất kỳ instance nào có thể tải phiên từ kho dùng chung. Hệ thống vẫn có thể bật affinity để tận dụng cache cục bộ hoặc giảm một phần truy cập kho dữ liệu, nhưng tính đúng đắn của phiên phải dựa trên repository dùng chung.

| Tiêu chí | Sticky session với phiên cục bộ | Spring Session với kho dùng chung |
| --- | --- | --- |
| Nơi giữ dữ liệu phiên | Bộ nhớ của một instance | Redis hoặc cơ sở dữ liệu dùng chung |
| Yêu cầu đến instance khác | Thường không tìm thấy phiên | Có thể tải cùng phiên |
| Khi instance bị dừng | Có thể mất phiên | Phiên còn trong kho nếu kho dữ liệu vẫn hoạt động |
| Phụ thuộc affinity | Thường có | Không cần cho tính đúng đắn |
| Chi phí truy cập | Ít truy cập kho ngoài | Có thêm truy cập mạng hoặc cơ sở dữ liệu |
| Thành phần cần vận hành | Load balancer và các instance | Load balancer, instance và kho phiên |

## 4. Nhân bản container và nhân bản phiên

Trong môi trường Docker hoặc Kubernetes, nhân bản container thường có nghĩa là chạy nhiều bản sao của cùng một ứng dụng, chẳng hạn nhiều container hoặc Pod cùng dùng một image. Mỗi bản sao có tiến trình, heap và bộ nhớ riêng. Tạo thêm container không khiến bộ nhớ trong các container tự động được chia sẻ.

Vì vậy, nếu ứng dụng vẫn lưu HttpSession trong bộ nhớ của servlet container, tăng số replica có thể làm lộ rõ vấn đề định tuyến phiên. Các replica cần một cách dùng chung trạng thái nếu người dùng có thể được định tuyến đến bất kỳ replica nào.

Có hai khái niệm cần phân biệt:

1. **Nhân bản ứng dụng/container:** chạy nhiều bản sao của ứng dụng để tăng năng lực xử lý, khả năng thay thế và khả năng phục vụ khi một bản sao gặp lỗi. Việc nhân bản này tự nó không nhân bản session.
2. **Nhân bản session của servlet container:** một số servlet container có cơ chế clustering để sao chép hoặc đồng bộ dữ liệu phiên giữa các node. Cơ chế này phụ thuộc vào container, cấu hình cụm, cách tuần tự hóa dữ liệu và cách truyền bản cập nhật.

Spring Session cung cấp một lựa chọn khác: lưu session trong repository dùng chung. Các instance không cần dựa vào cơ chế nhân bản session nội bộ của container để cùng truy cập trạng thái phiên. Khi đã chọn Spring Session làm chủ thể lưu trữ phiên, cần tránh cấu hình nhiều cơ chế cùng quản lý một phiên nếu chưa có thiết kế rõ ràng, vì có thể gây khó hiểu về nguồn dữ liệu thực tế.

### Kiến trúc thường dùng khi chạy nhiều replica

Một kiến trúc phổ biến là giữ các instance ứng dụng không lưu trạng thái phiên quan trọng trong bộ nhớ cục bộ, rồi dùng Redis hoặc JDBC làm kho phiên:

~~~mermaid
flowchart TD
    U["Người dùng"] --> L["Ingress / Load balancer"]
    L --> P1["Pod / Container 1<br/>Spring Boot + Spring Session"]
    L --> P2["Pod / Container 2<br/>Spring Boot + Spring Session"]
    L --> P3["Pod / Container N<br/>Spring Boot + Spring Session"]
    P1 --> R[("Redis dùng chung")]
    P2 --> R
    P3 --> R
    O["Giám sát, cảnh báo và sao lưu"] -.-> R
~~~

Khi tăng hoặc giảm số replica, mỗi bản sao mới chỉ cần kết nối đến cùng kho phiên và dùng cấu hình tương thích. Khi một replica bị thay thế, replica khác tiếp tục đọc phiên từ kho dữ liệu. Khả năng phục hồi khi Redis hoặc cơ sở dữ liệu gặp lỗi vẫn phải được thiết kế riêng; nhiều replica ứng dụng không thể tự bù cho một kho phiên đã ngừng hoạt động.

## 5. Cấu hình Spring Session với Redis

Redis thường được chọn khi cần truy cập phiên nhanh và có thể vận hành một kho dữ liệu dùng chung cho nhiều instance. Với Spring Boot, thêm các dependency tương thích với phiên bản Spring Boot đang dùng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Ví dụ cấu hình trong application.yml:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: spring:session:shop
      flush-mode: on-save
      save-mode: on-set-attribute
  data:
    redis:
      host: redis
      port: 6379
~~~

Ý nghĩa các cấu hình chính:

- store-type chọn Redis làm nơi lưu session khi ứng dụng có nhiều lựa chọn lưu trữ.
- timeout đặt thời gian không hoạt động tối đa của phiên. Cần chọn giá trị phù hợp với yêu cầu bảo mật và trải nghiệm người dùng.
- namespace tạo tiền tố riêng cho dữ liệu phiên của ứng dụng. Mỗi ứng dụng hoặc môi trường nên có namespace phù hợp để tránh dùng nhầm dữ liệu.
- flush-mode quyết định thời điểm thay đổi phiên được đẩy xuống Redis. on-save thường gom thay đổi và lưu khi kết thúc xử lý yêu cầu; chế độ lưu ngay có thể làm tăng số lần truy cập Redis.
- save-mode kiểm soát mức độ thuộc tính phiên được lưu. Chọn chế độ phù hợp giúp cân bằng giữa tính đơn giản và lượng dữ liệu cần ghi.

Spring Boot có thể tự cấu hình Spring Session khi các dependency và kết nối Redis cần thiết có mặt. Nếu ứng dụng không dùng cơ chế tự cấu hình của Spring Boot, có thể cấu hình thủ công bằng @EnableRedisHttpSession và cung cấp RedisConnectionFactory. Không nên bật hai cấu hình độc lập cùng quản lý repository nếu không có chủ đích rõ ràng.

Mọi replica của ứng dụng phải trỏ đến cùng Redis, dùng cùng namespace và các thiết lập session tương thích. Trong môi trường thật, bổ sung xác thực, TLS, quản lý secret, connection pool, timeout và cấu hình HA cho Redis theo hạ tầng đang vận hành. Không đưa mật khẩu Redis vào mã nguồn.

### Dùng JDBC thay cho Redis

Nếu hệ thống đã có cơ sở dữ liệu quan hệ và muốn lưu session cùng hạ tầng dữ liệu đó, có thể dùng Spring Session JDBC. Ứng dụng thêm module Spring Session JDBC, cấu hình DataSource dùng chung và để Spring Session quản lý các bảng lưu session. Các instance phải kết nối đến cùng cơ sở dữ liệu và cùng schema.

JDBC có thể phù hợp khi muốn giảm số loại hạ tầng phải vận hành hoặc cần tận dụng cơ chế giao dịch, sao lưu và quản trị cơ sở dữ liệu hiện có. Đổi lại, việc đọc và ghi session tạo thêm tải cho database. Cần đánh giá số lượng yêu cầu, kích thước session, connection pool, chỉ mục và chính sách dọn phiên hết hạn. Redis và JDBC đều có thể cung cấp kho phiên dùng chung; lựa chọn phụ thuộc vào yêu cầu tải, độ trễ, vận hành và độ bền dữ liệu.

## 6. Cookie, thời hạn và dữ liệu phiên

Trình duyệt thường gửi cookie session tự động trong các yêu cầu phù hợp với domain, path và chính sách SameSite. Cookie chỉ nên chứa mã phiên ngẫu nhiên, khó đoán. Dữ liệu người dùng và trạng thái nghiệp vụ được giữ phía máy chủ trong repository.

Khi dùng HTTPS trong môi trường production, cookie phiên nên có các thuộc tính bảo vệ phù hợp:

- HttpOnly hạn chế JavaScript phía trình duyệt đọc cookie.
- Secure yêu cầu trình duyệt chỉ gửi cookie qua kết nối HTTPS.
- SameSite giúp kiểm soát việc cookie được gửi trong yêu cầu xuất phát từ site khác; lựa chọn Lax, Strict hoặc None phải phù hợp với luồng điều hướng và đăng nhập của ứng dụng.
- Domain và Path cần giới hạn ở phạm vi ứng dụng cần sử dụng cookie.

Spring Session hỗ trợ cấu hình cookie thông qua CookieSerializer. Ví dụ bean sau minh họa cách đặt một số thuộc tính cơ bản; chỉ bật Secure khi ứng dụng được truy cập qua HTTPS:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
~~~

Thời hạn phiên phải được xác định rõ. Khi hết thời gian không hoạt động, repository sẽ coi phiên là hết hạn và người dùng cần tạo phiên mới hoặc đăng nhập lại. TTL trong kho dữ liệu cần phù hợp với timeout của ứng dụng. Không nên kéo dài phiên vô hạn chỉ để tránh người dùng phải đăng nhập lại.

Chỉ lưu các thuộc tính cần thiết trong session, ví dụ một mã người dùng, mã giỏ hàng hoặc một số tùy chọn nhỏ. Tránh lưu toàn bộ entity lớn, dữ liệu nhị phân, đối tượng phụ thuộc nhiều vào phiên bản lớp hoặc thông tin bí mật không cần thiết. Các thuộc tính phải tương thích với cơ chế tuần tự hóa mà repository đang dùng. Điều này đặc biệt quan trọng khi triển khai rolling update: hai phiên bản ứng dụng chạy đồng thời có thể cùng đọc dữ liệu phiên được ghi bởi phiên bản còn lại.

Sau khi xác thực thành công, cần áp dụng bảo vệ chống session fixation theo cơ chế bảo mật của ứng dụng và framework. Khi đăng xuất, vô hiệu hóa session để repository dùng chung không còn cung cấp phiên đó cho các instance khác. Xóa cookie ở trình duyệt cũng cần được xử lý với cùng tên, domain và path đã dùng khi tạo cookie.

## 7. Kiểm tra phiên có được chia sẻ giữa hai instance

Một kiểm tra thực tế nên chạy hai instance của cùng ứng dụng, cùng kết nối đến một Redis và cùng namespace. Để kiểm tra việc chia sẻ phiên, gửi hai yêu cầu trực tiếp đến hai cổng khác nhau với cùng cookie. Cách này giúp xác nhận repository hoạt động ngay cả khi không có sticky session.

Ví dụ endpoint đơn giản để kiểm tra:

~~~java
import jakarta.servlet.http.HttpSession;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class VisitController {

    @GetMapping("/visits")
    Map<String, Integer> visits(HttpSession session) {
        Integer count = (Integer) session.getAttribute("visits");
        count = (count == null) ? 1 : count + 1;
        session.setAttribute("visits", count);
        return Map.of("visits", count);
    }
}
~~~

Chạy ứng dụng ở hai cổng, chẳng hạn 8081 và 8082. Sau đó dùng cùng cookie jar cho hai yêu cầu:

~~~bash
curl -i -c session.cookie http://localhost:8081/visits
curl -i -b session.cookie http://localhost:8082/visits
~~~

Kết quả mong đợi là yêu cầu đầu tiên trả visits bằng 1, yêu cầu thứ hai trả visits bằng 2. Điều đó cho thấy instance thứ hai đã đọc được thuộc tính phiên do instance thứ nhất ghi. Cookie jar lưu cookie từ phản hồi đầu tiên và gửi lại trong yêu cầu thứ hai.

Nên kiểm tra thêm các tình huống sau:

1. Gửi nhiều yêu cầu luân phiên đến cả hai instance và xác nhận dữ liệu phiên vẫn được giữ.
2. Dừng instance đã tạo phiên, sau đó gửi yêu cầu đến instance còn lại. Phiên vẫn được đọc nếu dữ liệu trong kho dùng chung còn hiệu lực.
3. Đợi vượt quá timeout đã cấu hình và xác nhận phiên hết hạn theo thiết kế.
4. Đăng xuất ở một instance, sau đó gửi lại cookie cũ đến instance còn lại và xác nhận phiên đã bị vô hiệu hóa.
5. Tắt hoặc làm gián đoạn kết nối kho phiên trong môi trường kiểm thử để quan sát cách ứng dụng xử lý lỗi, thời gian chờ và cảnh báo.
6. Chạy kiểm thử đồng thời để phát hiện cập nhật thuộc tính bị ghi đè khi nhiều yêu cầu cùng đọc rồi sửa một phiên.

Ví dụ bộ đếm ở trên chỉ phù hợp để minh họa. Hai yêu cầu đồng thời có thể cùng đọc giá trị 5, cùng tính ra 6 rồi lần ghi cuối cùng ghi đè lần trước. Spring Session chia sẻ nơi lưu trữ, nhưng không biến mọi thao tác đọc-sửa-ghi trên thuộc tính session thành giao dịch nguyên tử. Với dữ liệu cần cập nhật đồng thời chính xác, hãy dùng thao tác nguyên tử của kho dữ liệu, giao dịch hoặc cơ chế đồng bộ phù hợp thay vì dựa vào bộ đếm trong HttpSession.

## 8. Vận hành nhiều instance

Khi chuyển từ một instance sang nhiều replica, cần kiểm tra cả ứng dụng, load balancer và kho phiên. Một số điểm vận hành quan trọng:

- **Tính sẵn sàng của kho phiên:** triển khai Redis hoặc database theo yêu cầu HA, đặt cảnh báo cho lỗi kết nối, độ trễ, dung lượng, số kết nối và tình trạng failover.
- **Giới hạn thời gian chờ:** cấu hình timeout và connection pool hợp lý để lỗi kho phiên không làm cạn tài nguyên của toàn bộ instance.
- **TTL và dung lượng:** đặt timeout phù hợp, theo dõi số lượng phiên và kích thước dữ liệu. Tránh giữ nhiều dữ liệu không còn cần thiết.
- **Khả năng tương thích khi cập nhật:** các phiên bản ứng dụng chạy song song trong rolling deployment cần đọc được cấu trúc session mà phiên bản khác đã ghi. Ưu tiên thuộc tính nhỏ, đơn giản và ổn định; có kế hoạch chuyển đổi khi thay đổi cấu trúc.
- **Phân vùng dữ liệu:** dùng namespace riêng cho từng ứng dụng và môi trường, trừ khi có thiết kế chia sẻ session được chủ đích. Chia sẻ Redis không có nghĩa mọi ứng dụng nên đọc cùng một tập phiên.
- **Bảo mật:** chỉ cho phép instance cần thiết truy cập kho phiên, mã hóa kết nối khi phù hợp, quản lý secret an toàn và không ghi session ID hoặc nội dung nhạy cảm vào log.
- **Giám sát sự kiện:** nếu nghiệp vụ cần xử lý sự kiện tạo, hết hạn hoặc xóa session, kiểm tra cấu hình phát sự kiện của repository và khả năng nhận sự kiện trong môi trường nhiều node. Không giả định mọi thông báo hết hạn đều được phát chính xác nếu hạ tầng Redis chưa cấu hình cơ chế thông báo cần thiết.

Khi kho phiên không truy cập được, các yêu cầu cần đọc hoặc ghi session có thể thất bại. Cần xác định rõ ứng dụng sẽ trả lỗi, yêu cầu đăng nhập lại hay áp dụng chính sách khác. Tự động chuyển sang session cục bộ trong lúc Redis lỗi thường tạo ra hai nguồn trạng thái không đồng nhất: một yêu cầu có thể ghi phiên vào Redis, yêu cầu sau lại đọc một phiên khác trong bộ nhớ instance. Chỉ dùng cơ chế dự phòng nếu đã thiết kế và kiểm thử rõ cách đồng bộ, khôi phục và xử lý xung đột.

## 9. Chọn cách triển khai

Có thể dùng các nguyên tắc sau khi lựa chọn:

| Nhu cầu | Hướng triển khai phù hợp |
| --- | --- |
| Một instance, ứng dụng nhỏ, chấp nhận mất phiên khi khởi động lại | Session mặc định trong servlet container có thể đáp ứng |
| Nhiều replica và cần phiên tồn tại khi yêu cầu chuyển node | Spring Session với Redis hoặc JDBC |
| Muốn tận dụng cache cục bộ và chấp nhận phụ thuộc backend | Có thể cân nhắc sticky session, đồng thời đánh giá tình huống backend lỗi |
| Đang dùng clustering của servlet container | Đánh giá khả năng tương thích và chi phí vận hành; không mặc định rằng nhân bản container đồng nghĩa với Spring Session |
| Cần scale ngang trên Docker hoặc Kubernetes | Nhiều replica ứng dụng kết hợp kho phiên dùng chung là mô hình phổ biến |

Với ứng dụng Spring cần chạy trên nhiều instance, Spring Session kết hợp Redis hoặc JDBC thường tạo ra ranh giới rõ ràng giữa xử lý yêu cầu và lưu trạng thái phiên. Sticky session có thể là tối ưu định tuyến tùy chọn. Việc nhân bản container giúp tăng năng lực và khả năng thay thế của ứng dụng; kho phiên dùng chung mới là thành phần cho phép các replica tiếp tục làm việc với cùng trạng thái người dùng.
