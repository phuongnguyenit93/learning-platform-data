# View tương đối với flow và ViewResolver dùng chung

## 1. Vai trò của view trong Spring Web Flow và Spring MVC

Trong Spring Web Flow, một `view-state` mô tả màn hình mà người dùng đang tương tác. Thuộc tính `view` của state xác định tên view cần hiển thị. Flow xử lý event, thực hiện transition và quyết định view-state tiếp theo; Spring MVC đảm nhiệm việc phân giải tên view thành giao diện thực tế và render phản hồi HTTP.

Hai phần cần phối hợp:

- **Spring Web Flow** quản lý state, event, dữ liệu flow và thời điểm hiển thị view.
- **Spring MVC ViewResolver** chuyển tên view logic thành một đối tượng `View` cụ thể, chẳng hạn JSP, Thymeleaf hoặc một loại view khác mà ứng dụng hỗ trợ.

Ví dụ, flow đặt chỗ có thể khai báo:

~~~xml
<view-state id="enterDetails" view="booking/enterDetails">
    <transition on="continue" to="review"/>
</view-state>
~~~

Tên `booking/enterDetails` là tên view logic. Nó chưa nhất thiết là đường dẫn file trên đĩa. Một `ViewResolver` có thể chuyển tên này thành `/WEB-INF/views/booking/enterDetails.jsp`, hoặc một template tương ứng nếu ứng dụng dùng Thymeleaf.

Bài học này thuộc chương **Tích hợp Spring MVC** của module **SPRING_WEB_FLOW**. Khi mô hình hóa hành trình nhiều bước bằng state, event, transition và subflow, việc tổ chức tên view theo flow và dùng chung cơ chế phân giải view giúp giao diện nhất quán, cấu hình ít trùng lặp và dễ kiểm thử.

## 2. Tên view logic và đường dẫn view vật lý

Không nên nhầm lẫn ba giá trị sau:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| View-state ID | `enterDetails` | Định danh state trong flow definition |
| View logic name | `booking/enterDetails` | Tên mà flow yêu cầu hiển thị |
| Đường dẫn view vật lý | `/WEB-INF/views/booking/enterDetails.jsp` | Tài nguyên template được resolver chọn |

View-state ID dùng trong điều hướng của flow. Tên view logic dùng để phân giải giao diện. Đường dẫn vật lý phụ thuộc công nghệ view và cấu hình resolver.

Ví dụ, một `InternalResourceViewResolver` có thể được cấu hình như sau:

~~~xml
<bean id="jspViewResolver"
      class="org.springframework.web.servlet.view.InternalResourceViewResolver">
    <property name="prefix" value="/WEB-INF/views/"/>
    <property name="suffix" value=".jsp"/>
</bean>
~~~

Với cấu hình này, tên logic `booking/enterDetails` được ghép với prefix và suffix để tạo đường dẫn `/WEB-INF/views/booking/enterDetails.jsp`.

Nếu đổi giao diện sang Thymeleaf, ứng dụng có thể thay resolver bằng `ThymeleafViewResolver` và cấu hình template tương ứng. Flow vẫn có thể dùng tên logic ổn định nếu quy ước tên view được giữ nhất quán.

Đây là lợi ích của view logic name: flow không cần biết trực tiếp phần mở rộng file hoặc vị trí triển khai template.

## 3. Tổ chức view tương đối với flow

### 3.1. Nhóm view theo chức năng của flow

Khi một ứng dụng có nhiều hành trình, nên tổ chức view theo nhóm nghiệp vụ hoặc theo flow để tránh tên trùng và giúp người phát triển tìm đúng template.

Ví dụ:

~~~text
/WEB-INF/views/
    booking/
        enterDetails.jsp
        selectRoom.jsp
        review.jsp
        completed.jsp
    checkout/
        shipping.jsp
        payment.jsp
        confirmation.jsp
    account/
        editProfile.jsp
        profileUpdated.jsp
    common/
        flowError.jsp
        sessionExpired.jsp
~~~

Flow đặt chỗ tham chiếu các view trong nhóm `booking`; flow thanh toán dùng nhóm `checkout`. Cách đặt tên này tạo một quy ước tương đối theo chức năng flow, đồng thời vẫn dùng chung một view root của ứng dụng.

Ví dụ trong flow đặt chỗ:

~~~xml
<view-state id="enterDetails" view="booking/enterDetails">
    <transition on="next" to="selectRoom"/>
</view-state>

<view-state id="selectRoom" view="booking/selectRoom">
    <transition on="back" to="enterDetails"/>
    <transition on="next" to="review"/>
</view-state>

<view-state id="review" view="booking/review">
    <transition on="confirm" to="completed"/>
</view-state>

<end-state id="completed"/>
~~~

Ở đây, `booking/enterDetails`, `booking/selectRoom` và `booking/review` là các tên logic có cùng tiền tố `booking/`. Chúng tạo thành một nhóm dễ nhận diện và tránh đụng tên với view của flow khác.

### 3.2. Flow-relative name và quy ước phân giải

Một số cấu hình ứng dụng sử dụng khái niệm **flow-relative view name**: tên view được diễn giải trong ngữ cảnh của flow đang chạy. Ví dụ, một flow có thể khai báo tên ngắn `enterDetails`, còn cơ chế phân giải sẽ xác định nhóm view tương ứng với flow đó.

Điểm quan trọng là hành vi này phụ thuộc vào `ViewFactoryCreator`, resolver và quy ước đặt tên mà ứng dụng cấu hình. Không nên mặc định rằng mọi tên ngắn đều tự động được nối với thư mục chứa flow definition. Nếu muốn dùng tên tương đối, hãy xác định rõ quy tắc ánh xạ và kiểm thử kết quả phân giải.

Một quy ước đơn giản, dễ kiểm soát là dùng tên có namespace chức năng ngay trong flow XML:

~~~xml
<view-state id="enterDetails" view="booking/enterDetails"/>
~~~

Khi cần resolver tự bổ sung tiền tố theo flow, hãy cấu hình cơ chế flow-relative tương ứng và ghi rõ cách ánh xạ trong dự án. Tránh đồng thời vừa thêm tiền tố trong XML vừa thêm lại cùng tiền tố ở resolver, vì kết quả có thể thành `booking/booking/enterDetails`.

### 3.3. Không dùng đường dẫn vật lý làm tên view nếu không cần thiết

Ví dụ sau gắn flow với một vị trí triển khai cụ thể:

~~~xml
<view-state id="enterDetails"
            view="/WEB-INF/views/booking/enterDetails.jsp"/>
~~~

Cách này có thể hoạt động với một số cấu hình view, nhưng làm flow phụ thuộc vào công nghệ và vị trí file. Nếu sau này chuyển JSP sang Thymeleaf hoặc đổi thư mục template, phải sửa nhiều flow definition.

Tên logic thường linh hoạt hơn:

~~~xml
<view-state id="enterDetails" view="booking/enterDetails"/>
~~~

Chỉ sử dụng đường dẫn vật lý khi ứng dụng có lý do rõ ràng và đã thống nhất cách resolver xử lý nó.

## 4. Dùng chung ViewResolver giữa Spring MVC và Spring Web Flow

### 4.1. Vì sao nên chia sẻ resolver?

Trong một ứng dụng Spring MVC có cả controller thông thường và flow, cả hai loại request đều cần render view. Nếu mỗi phần tự cấu hình một resolver độc lập, ứng dụng có thể gặp các khác biệt khó phát hiện:

- Controller tìm template ở một thư mục, flow lại tìm ở thư mục khác.
- Một tên logic cho kết quả JSP trong MVC nhưng không được flow phân giải.
- Quy tắc prefix, suffix, locale hoặc theme không nhất quán.
- Cùng một view được cấu hình hai lần với hành vi khác nhau.

Dùng chung một hoặc một danh sách `ViewResolver` phù hợp giúp Spring MVC và Spring Web Flow hiểu cùng một hệ tên view logic. Với Spring Web Flow MVC, `MvcViewFactoryCreator` nhận danh sách resolver để tạo view cho các `view-state`.

### 4.2. Cấu hình XML minh họa

Ví dụ dưới đây dùng JSP và một resolver chung:

~~~xml
<bean id="jspViewResolver"
      class="org.springframework.web.servlet.view.InternalResourceViewResolver">
    <property name="prefix" value="/WEB-INF/views/"/>
    <property name="suffix" value=".jsp"/>
</bean>

<bean id="mvcViewFactoryCreator"
      class="org.springframework.webflow.mvc.builder.MvcViewFactoryCreator">
    <property name="viewResolvers">
        <list>
            <ref bean="jspViewResolver"/>
        </list>
    </property>
</bean>

<webflow:flow-builder-services
        id="flowBuilderServices"
        view-factory-creator="mvcViewFactoryCreator"/>
~~~

Phần khai báo namespace `webflow` cần có trong file cấu hình tương ứng. Flow registry và flow executor cũng phải được cấu hình trong ứng dụng theo kiến trúc triển khai.

Trong Spring MVC, `DispatcherServlet` sử dụng `ViewResolver` được đăng ký trong `WebApplicationContext` của nó. Cấu hình Web Flow dùng `MvcViewFactoryCreator` cũng tham chiếu tới bean `jspViewResolver`. Vì vậy, cả controller và flow có thể phân giải tên `booking/review` theo cùng prefix và suffix.

Khi dùng nhiều resolver, danh sách trong `MvcViewFactoryCreator` phải phản ánh thứ tự ưu tiên phù hợp với ứng dụng. Các resolver chuyên biệt thường được đặt trước resolver tổng quát. `InternalResourceViewResolver` thường nên ở cuối vì nó có thể tạo view cho nhiều tên ngay cả khi file JSP tương ứng không tồn tại; nếu đặt quá sớm, resolver này có thể che khuất resolver template khác.

### 4.3. Vị trí đăng ký bean và context hierarchy

Cần bảo đảm `ViewResolver` và `MvcViewFactoryCreator` nằm trong các context có thể nhìn thấy nhau.

Trong cấu trúc Spring MVC có root context và child context của `DispatcherServlet`:

- Root context thường chứa service và repository dùng chung.
- Child context thường chứa controller, cấu hình MVC, view resolver và các thành phần tích hợp Web Flow của servlet.
- Child context có thể truy cập bean ở root context.
- Root context không tự nhìn thấy bean chỉ được khai báo trong child context.

Một cách tổ chức thường gặp là đặt view resolver và cấu hình Web Flow MVC trong context của `DispatcherServlet` xử lý các request flow. Nếu đặt `MvcViewFactoryCreator` ở context khác, phải kiểm tra rõ bean resolver có thể được inject và được dùng đúng nơi hay không.

Tránh khai báo hai bean resolver cùng tên logic nhưng có prefix/suffix khác nhau ở root và child context. Việc shadow bean hoặc dùng nhầm instance có thể khiến controller và flow render hai kết quả khác nhau.

## 5. Tích hợp với FlowHandlerMapping và FlowHandlerAdapter

Để Spring MVC chuyển request tới flow, ứng dụng thường cấu hình `FlowHandlerMapping` và `FlowHandlerAdapter`.

Ví dụ cấu hình rút gọn:

~~~xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry"/>
    <property name="order" value="1"/>
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor"/>
</bean>
~~~

`FlowHandlerMapping` tìm flow phù hợp với request dựa trên registry và quy tắc mapping. `FlowHandlerAdapter` chuyển request tới `FlowExecutor` để bắt đầu hoặc tiếp tục flow execution.

Hai thành phần này đảm nhiệm định tuyến request và thực thi flow. `MvcViewFactoryCreator` cùng danh sách `ViewResolver` đảm nhiệm việc tạo view cho view-state. Đây là các trách nhiệm liên quan nhưng khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `FlowHandlerMapping` | Xác định request thuộc flow nào |
| `FlowHandlerAdapter` | Chuyển request tới flow executor |
| `FlowExecutor` | Bắt đầu, tiếp tục và kết thúc flow execution |
| `MvcViewFactoryCreator` | Tạo view factory cho view-state |
| `ViewResolver` | Phân giải tên view logic thành `View` |

Một cấu hình flow có thể điều hướng đúng state nhưng vẫn không render được view nếu resolver không tìm thấy template. Ngược lại, template tồn tại không có nghĩa request đã được mapping tới đúng flow.

## 6. Ví dụ hoàn chỉnh về quy ước tên view

Giả sử ứng dụng có flow `booking` được đăng ký từ tài nguyên flow của nghiệp vụ đặt chỗ. Các view được lưu dưới `/WEB-INF/views/booking/`. Resolver JSP dùng prefix `/WEB-INF/views/` và suffix `.jsp`.

Flow XML:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">

    <view-state id="enterDetails" view="booking/enterDetails">
        <transition on="continue" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="enterDetails"/>
        <transition on="confirm" to="complete"/>
    </view-state>

    <end-state id="complete"/>
</flow>
~~~

Ánh xạ view:

| View logic name | ViewResolver tạo đường dẫn |
| --- | --- |
| `booking/enterDetails` | `/WEB-INF/views/booking/enterDetails.jsp` |
| `booking/review` | `/WEB-INF/views/booking/review.jsp` |

Controller thông thường có thể trả về cùng tên logic:

~~~java
@Controller
public class BookingHelpController {

    @GetMapping("/booking/help")
    public String help() {
        return "booking/help";
    }
}
~~~

Với resolver chung, controller có thể render `/WEB-INF/views/booking/help.jsp`, trong khi flow render các template `enterDetails` và `review` theo cùng quy tắc. Việc chia sẻ tên logic giúp nhóm phát triển dùng một quy ước nhất quán dù view được mở từ controller hay từ flow.

## 7. Resolver chain, thứ tự ưu tiên và tên view trùng nhau

Một ứng dụng có thể dùng nhiều loại view, ví dụ Thymeleaf cho trang HTML, PDF view cho tài liệu và JSP cho một số màn hình cũ. Khi đó, resolver chain cần có thứ tự rõ ràng.

Ví dụ về nguyên tắc sắp xếp:

1. Resolver chuyên biệt cho loại view hoặc namespace cụ thể.
2. Resolver template chính của ứng dụng.
3. Resolver tổng quát hoặc fallback.
4. Resolver có khả năng nhận hầu hết tên view nên đặt cuối nếu nó có thể che các resolver khác.

Tên view nên có namespace theo chức năng, chẳng hạn `booking/review`, `account/profile` hoặc `common/error`. Tránh đặt tên chung chung như `success`, `form` hoặc `detail` ở nhiều thư mục mà không có quy ước rõ ràng.

Nếu hai resolver đều có thể phân giải cùng một tên, kết quả phụ thuộc thứ tự và cách resolver xử lý tên không tìm thấy. Vì vậy, kiểm thử phải xác nhận resolver nào được chọn cho mỗi nhóm view quan trọng.

## 8. Locale, theme và các thuộc tính render

Spring MVC có thể sử dụng locale resolver, theme resolver và các thành phần phục vụ nội dung hiển thị. Khi flow dùng cùng cơ chế view resolution, cần kiểm tra view được render trong đúng ngữ cảnh request để các thuộc tính như locale, theme và model được áp dụng như mong đợi.

Một số điểm cần lưu ý:

- Thông báo validation nên dùng message code và message source thay vì hard-code chuỗi vào flow.
- Tên view logic không nên chứa thông tin người dùng hoặc dữ liệu request.
- Dữ liệu cần render phải được đưa vào model phù hợp của view-state.
- Các view dùng chung cho lỗi hoặc hết phiên nên được tổ chức rõ ràng và có đường điều hướng an toàn.
- Không đưa dữ liệu nhạy cảm vào model chỉ để tiện hiển thị.

Nếu flow chạy trong nhiều `DispatcherServlet`, mỗi servlet có thể có context và resolver riêng. Cần xác nhận flow được xử lý bởi servlet nào và view resolver nào thực sự phục vụ request đó.

## 9. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Flow vào đúng view-state nhưng báo không tìm thấy view | Tên logic không khớp resolver hoặc template thiếu | Kiểm tra `view` trong flow, prefix/suffix và vị trí template |
| Controller render được nhưng flow không render được cùng tên | `MvcViewFactoryCreator` chưa dùng resolver của MVC hoặc dùng danh sách khác | Kiểm tra thuộc tính `viewResolvers` và context chứa bean |
| Flow tìm sai thư mục view | Tiền tố flow-relative bị thiếu hoặc bị thêm hai lần | Kiểm tra quy ước tên và cơ chế relative resolution |
| JSP được chọn thay cho Thymeleaf | Resolver JSP đứng trước và nhận tên quá rộng | Điều chỉnh thứ tự resolver; đặt resolver tổng quát ở cuối |
| View của flow A bị trùng với flow B | Dùng tên chung không có namespace | Dùng nhóm tên như `booking/...` và `checkout/...` |
| Bean resolver không được inject | Bean nằm trong context không nhìn thấy từ cấu hình Web Flow | Kiểm tra root/child context và vị trí đăng ký |
| Flow request không tới `FlowHandlerAdapter` | Mapping hoặc order của handler không phù hợp | Kiểm tra URL flow, registry và thứ tự handler mapping |

Khi điều tra, hãy ghi nhận bốn thông tin: request URL, flow ID/state ID, view logic name và resolver thực tế được gọi. Bốn thông tin này giúp tách lỗi định tuyến flow khỏi lỗi phân giải template.

## 10. Kiểm thử cấu hình view

Kiểm thử cần xác nhận cả đường đi của flow và kết quả phân giải view.

### 10.1. Kiểm thử resolver độc lập

- Gọi resolver với tên logic `booking/review`.
- Xác nhận nó tạo đúng loại `View`.
- Kiểm tra đường dẫn hoặc template được chọn đúng prefix/suffix.
- Kiểm tra tên không tồn tại được xử lý theo chính sách fallback của ứng dụng.

### 10.2. Kiểm thử tích hợp Spring MVC

- Gửi request tới controller trả về `booking/help`.
- Xác nhận `DispatcherServlet` dùng resolver dự kiến.
- Gửi request bắt đầu flow và xác nhận view-state được render bằng cùng quy ước.
- Kiểm tra thứ tự resolver khi có nhiều loại template.

### 10.3. Kiểm thử flow execution

- Bắt đầu flow và xác nhận view đầu tiên được phân giải.
- Gửi event để chuyển sang view-state kế tiếp và xác nhận view logic name mới được dùng.
- Kiểm tra transition quay lại state trước vẫn render đúng template.
- Kiểm tra event validation lỗi giữ người dùng ở view-state và hiển thị thông báo đúng.
- Kiểm tra flow hết hạn hoặc lỗi có thể hiển thị view lỗi phù hợp.

Nên có ít nhất một kiểm thử cho flow và một kiểm thử cho controller dùng chung tên view logic. Điều này giúp phát hiện trường hợp hai đường render vô tình dùng resolver khác nhau.

## 11. Quy trình tổ chức view và resolver

Khi thêm một view-state mới, hãy thực hiện theo trình tự:

1. **Xác định flow sở hữu màn hình.** Chọn namespace chức năng để tránh trùng tên với flow khác.
2. **Đặt tên view logic.** Dùng tên ổn định như `booking/review`, không gắn đuôi `.jsp` nếu resolver chịu trách nhiệm chọn template.
3. **Tạo template ở vị trí đã quy ước.** Kiểm tra prefix/suffix hoặc template root của resolver.
4. **Đăng ký resolver dùng chung.** Bảo đảm `DispatcherServlet` và `MvcViewFactoryCreator` dùng cùng cấu hình thích hợp.
5. **Kiểm tra flow-relative resolution nếu sử dụng.** Xác nhận tên ngắn được ánh xạ đúng một lần và không thêm prefix trùng.
6. **Kiểm tra context hierarchy.** Xác nhận các bean resolver và view factory có thể nhìn thấy nhau.
7. **Kiểm thử cả controller và flow.** Render cùng một nhóm tên logic để bảo đảm kết quả nhất quán.

Với ứng dụng đặt chỗ, flow dùng các tên `booking/enterDetails`, `booking/review` và `booking/completed`; controller trợ giúp có thể trả về `booking/help`. Cùng một resolver tạo ra các view tương ứng trong thư mục `booking`. Flow giữ trách nhiệm điều hướng; Spring MVC giữ trách nhiệm phân giải và render giao diện.

## 12. Tự kiểm tra

- View-state ID có phải đường dẫn file JSP không? Không. Nó định danh state trong flow.
- Thuộc tính `view` thường chứa gì? Tên view logic được view factory/resolver xử lý.
- `ViewResolver` làm nhiệm vụ gì? Chuyển tên logic thành một đối tượng `View`.
- Vì sao nên dùng chung resolver giữa MVC và Web Flow? Để tên view, prefix/suffix và quy tắc render nhất quán.
- `MvcViewFactoryCreator` nhận resolver qua thuộc tính nào? `viewResolvers`.
- Flow-relative view name có tự động hoạt động giống nhau trong mọi ứng dụng không? Không. Cần kiểm tra cơ chế và quy ước resolver đã cấu hình.
- Nếu controller render được nhưng flow không render được, cần kiểm tra gì? Danh sách resolver của `MvcViewFactoryCreator`, context chứa bean và tên view logic.
- Vì sao resolver tổng quát thường nên ở cuối? Nó có thể nhận tên quá rộng và che khuất resolver chuyên biệt.

Tổ chức view theo flow và chia sẻ cấu hình `ViewResolver` giúp Spring Web Flow phối hợp tự nhiên với Spring MVC. Khi tên view logic, resolver chain và context hierarchy được xác định rõ, các màn hình của hành trình nhiều bước sẽ dễ tổ chức, render nhất quán và thuận tiện kiểm thử hơn.

