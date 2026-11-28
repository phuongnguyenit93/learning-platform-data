# Lưu phiên khi kết thúc xử lý hoặc trước lúc phản hồi được commit

Trong ứng dụng Servlet dùng Spring Session, dữ liệu phiên được lưu qua một SessionRepository như Redis hoặc JDBC. Ứng dụng vẫn thao tác với HttpSession bằng Servlet API, còn Spring Session chịu trách nhiệm đồng bộ trạng thái phiên với kho lưu trữ. Một điểm quan trọng của tích hợp này là thời điểm lưu: thay đổi phiên thường được ghi khi request kết thúc hoặc ngay trước khi response được commit, để cookie phiên và dữ liệu phiên được cập nhật kịp thời trước khi phản hồi rời khỏi máy chủ.

Hiểu thời điểm này giúp tránh lỗi như redirect về trang kế tiếp nhưng trang đó không thấy dữ liệu vừa thêm, response đã gửi mà cookie phiên chưa được đặt, hoặc thuộc tính phiên được thay đổi sau khi luồng xử lý đã kết thúc.

## 1. Hai thời điểm cần hiểu: kết thúc request và commit response

**Kết thúc xử lý request** là lúc chuỗi filter và servlet hoàn tất việc xử lý request hiện tại. Ở giai đoạn này, Spring Session có thể lưu phiên đã được tạo hoặc thay đổi trong request.

**Commit response** là thời điểm container bắt đầu gửi trạng thái response, header và nội dung đến client theo cách không còn có thể thay đổi tùy ý. Trước thời điểm này, ứng dụng có thể bổ sung header, cookie hoặc điều chỉnh status. Sau khi response đã commit, việc thêm cookie session ID hoặc sửa header có thể không còn tác dụng.

Hai thời điểm có thể xảy ra theo thứ tự khác nhau. Với response nhỏ, ứng dụng có thể hoàn tất xử lý rồi container mới commit response. Với redirect, sendError, flushBuffer hoặc ghi nội dung đủ làm đầy buffer, response có thể commit ngay trong khi request vẫn đang chạy. Vì vậy, Spring Session cần cơ chế lưu phiên trước khi response được commit, ngoài bước lưu khi chuỗi xử lý kết thúc.

Ví dụ, endpoint thêm một sản phẩm vào giỏ hàng rồi redirect:

~~~java
@PostMapping("/cart/items")
public String addItem(HttpServletRequest request) {
    HttpSession session = request.getSession();
    Cart cart = (Cart) session.getAttribute("cart");

    if (cart == null) {
        cart = new Cart();
    }

    cart.add("BOOK-01");
    session.setAttribute("cart", cart);

    return "redirect:/cart";
}
~~~

Khi Spring MVC xử lý kết quả redirect, response có thể được gửi bằng sendRedirect. Spring Session phải lưu dữ liệu giỏ hàng và đặt cookie phiên trước khi response redirect được commit. Trình duyệt nhận redirect, gửi request GET mới kèm cookie; request mới có thể tải phiên và đọc giỏ hàng vừa cập nhật.

Nếu dữ liệu phiên chỉ được ghi sau khi response đã commit, request kế tiếp có thể đến trước khi dữ liệu mới được lưu hoặc client có thể không nhận được cookie cần thiết. Đây là lý do cơ chế tích hợp theo dõi cả quá trình commit response.

## 2. Spring Session can thiệp vào Servlet request như thế nào?

Trong ứng dụng Servlet, thành phần trung tâm là SessionRepositoryFilter. Bộ lọc này bọc HttpServletRequest và HttpServletResponse bằng các wrapper tương thích với Servlet API. Khi controller hoặc Spring Security gọi request.getSession(), wrapper trả về phiên do Spring Session quản lý thay vì để ứng dụng làm việc trực tiếp với session cục bộ của container.

Luồng khái quát:

    Trình duyệt
        |
        | Request có cookie session ID
        v
    SessionRepositoryFilter
        |
        | Đọc ID và tải phiên từ repository
        v
    Spring Security và các filter khác
        |
        v
    DispatcherServlet / Controller
        |
        | Tạo hoặc thay đổi HttpSession
        v
    Response wrapper theo dõi thao tác commit
        |
        | Lưu phiên và ghi cookie nếu cần
        v
    Servlet container commit response
        |
        v
    Trình duyệt nhận response và cookie

Bộ lọc có hai điểm kiểm soát quan trọng:

1. Nó giữ tham chiếu đến phiên được tải hoặc tạo trong request và theo dõi trạng thái thay đổi.
2. Nó có thể yêu cầu lưu phiên khi response sắp commit và khi chuỗi filter hoàn tất.

Việc lưu phiên và việc ghi cookie liên quan chặt chẽ nhưng là hai thao tác riêng. Repository lưu dữ liệu phiên ở máy chủ; cookie gửi session ID về trình duyệt để các request sau tìm lại phiên. Nếu phiên mới được tạo, response cần có cookie tương ứng. Nếu phiên hiện tại được giữ nguyên ID, response thường không cần tạo ID mới, trừ khi có chiến lược đổi ID hoặc cập nhật cookie.

Spring Session làm cho các lời gọi Servlet API quen thuộc tiếp tục hoạt động, nhưng không có nghĩa mọi thao tác với response đều được trì hoãn. Khi response sắp commit, bộ lọc cần lưu phiên trước khi giao quyền commit cho container.

## 3. Lưu phiên trước response commit

Một response có thể commit qua nhiều đường đi, không chỉ khi method controller trả về. Những thao tác thường có thể kích hoạt commit gồm:

- Gọi HttpServletResponse.sendRedirect().
- Gọi HttpServletResponse.sendError().
- Gọi ServletResponse.flushBuffer().
- Ghi dữ liệu ra response và làm bộ đệm của container đầy.
- Đóng writer hoặc output stream trong tình huống container hoàn tất phản hồi.

Response wrapper của Spring Session theo dõi các thao tác commit liên quan. Trước khi ủy quyền thao tác commit cho response gốc, wrapper yêu cầu request wrapper hoàn tất việc lưu phiên. Sau đó, cookie session ID cần thiết được ghi vào header trước khi container gửi header và body.

Ví dụ về thứ tự mong muốn:

1. Controller lấy phiên hiện tại.
2. Controller thay đổi thuộc tính giỏ hàng.
3. Controller trả về redirect.
4. Cơ chế xử lý redirect gọi sendRedirect.
5. Spring Session lưu phiên và cập nhật cookie cần thiết.
6. Response gốc được commit.
7. Trình duyệt nhận redirect và cookie mới hoặc cookie hiện hành.

Điều này cũng giải thích tại sao không nên ghi hoặc flush response quá sớm rồi mới tạo phiên. Một khi response đã commit, server không thể đảm bảo cookie được bổ sung vào response đó. Hãy tạo hoặc thay đổi phiên trước thao tác có khả năng commit response.

## 4. Lưu phiên khi chuỗi xử lý request hoàn tất

Không phải mọi request đều commit response sớm. Với response bình thường, Spring Session cũng có thể lưu phiên khi việc thực thi chuỗi filter kết thúc. Đây là điểm chốt cho các thay đổi phát sinh trong controller hoặc filter trong suốt request.

Một ví dụ đơn giản:

~~~java
@GetMapping("/preferences/theme")
public String chooseTheme(
        @RequestParam String theme,
        HttpServletRequest request) {

    HttpSession session = request.getSession();
    session.setAttribute("theme", theme);

    return "Theme updated";
}
~~~

Nếu response chưa commit trong quá trình controller chạy, phiên có thể được lưu khi filter hoàn tất xử lý request. Khi đó, request tiếp theo dùng cookie phiên sẽ tải được thuộc tính theme.

Việc lưu ở cuối request tạo một ranh giới tự nhiên: ứng dụng thực hiện các thao tác đọc/ghi phiên trong lúc xử lý, sau đó Spring Session đồng bộ trạng thái cuối cùng vào repository. Cách này hạn chế việc ghi kho dữ liệu sau mỗi lần setAttribute nếu repository đang dùng chế độ flush khi save.

Tuy vậy, cuối request không phải một transaction nghiệp vụ bao trùm mọi hệ thống. Nếu controller đã ghi dữ liệu vào cơ sở dữ liệu nghiệp vụ rồi sau đó lưu session thất bại, hai thao tác không tự động rollback cùng nhau. Ứng dụng cần thiết kế xử lý lỗi và tính nhất quán theo yêu cầu nghiệp vụ.

## 5. Phân biệt FlushMode và SaveMode

Spring Session có hai nhóm thiết lập liên quan đến cách ghi phiên. Chúng giải quyết hai câu hỏi khác nhau.

**FlushMode** quyết định khi nào thay đổi của phiên được đẩy xuống kho dữ liệu:

| Chế độ | Ý nghĩa | Tác động thường gặp |
|---|---|---|
| ON_SAVE | Ghi các thay đổi khi repository nhận lệnh save phiên | Giảm số lần ghi; thay đổi được gom đến điểm lưu |
| IMMEDIATE | Ghi thay đổi sớm nhất có thể khi chúng phát sinh | Dữ liệu được đẩy sớm hơn nhưng có thể tăng số lần ghi |

Với Servlet integration, ON_SAVE thường phù hợp khi muốn gom thay đổi và lưu ở cuối request hoặc trước response commit. IMMEDIATE hữu ích khi cần các thay đổi được ghi sớm hơn, nhưng cần cân nhắc chi phí I/O và hành vi cập nhật đồng thời.

**SaveMode** quyết định những thuộc tính nào được ghi khi lưu phiên:

| Chế độ | Ý nghĩa |
|---|---|
| ON_SET_ATTRIBUTE | Ghi các thuộc tính đã được đặt hoặc cập nhật trong phiên theo cơ chế theo dõi của repository |
| ON_GET_ATTRIBUTE | Ghi cả thuộc tính được đọc, bên cạnh các thuộc tính được đặt |
| ALWAYS | Ghi tất cả thuộc tính phiên khi lưu |

SaveMode đặc biệt hữu ích khi đối tượng được lưu trong phiên có thể thay đổi bên trong mà không gọi lại setAttribute. Ví dụ:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add("BOOK-02");
~~~

Đoạn mã trên sửa đối tượng Cart đang nằm trong phiên nhưng không gọi session.setAttribute("cart", cart). Với chế độ chỉ theo dõi thuộc tính được đặt, repository có thể không nhận ra thay đổi bên trong đối tượng. Có thể đặt lại thuộc tính sau khi sửa:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add("BOOK-02");
session.setAttribute("cart", cart);
~~~

Hoặc chọn SaveMode phù hợp với yêu cầu và repository. Việc ghi tất cả thuộc tính có thể tăng chi phí serialization và I/O, vì vậy nên ưu tiên mô hình cập nhật rõ ràng, dễ theo dõi.

Các giá trị cấu hình và phạm vi hỗ trợ có thể khác theo repository và phiên bản Spring Session. Không nên giả định mọi kho dữ liệu đều có cùng tập thuộc tính cấu hình chuyên biệt. Hãy xác nhận cấu hình của module đang sử dụng.

## 6. Ví dụ cấu hình Redis với ON_SAVE

Với Spring Boot và Spring Session Redis, có thể cấu hình thời điểm flush và cách theo dõi thuộc tính trong application.yml. Ví dụ dưới đây minh họa cấu hình thường gặp ở các phiên bản Boot có hỗ trợ các thuộc tính này:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      flush-mode: on-save
      save-mode: on-set-attribute
      namespace: shop:session
~~~

Với cấu hình ON_SAVE, Spring Session giữ các thay đổi trong đối tượng phiên đang xử lý và ghi chúng khi repository được yêu cầu lưu. Trong tích hợp Servlet, điểm lưu thường là lúc request kết thúc hoặc trước khi response commit.

Có thể cấu hình bằng Java khi bật repository thủ công. Ví dụ khái niệm:

~~~java
@Configuration
@EnableRedisHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE,
    maxInactiveIntervalInSeconds = 1800
)
class SessionConfiguration {
}
~~~

Nếu ứng dụng đang dùng cấu hình tự động của Boot, không nên thêm annotation bật repository thủ công chỉ để đặt một thuộc tính mà Boot đã hỗ trợ. Chọn một cơ chế cấu hình nhất quán và tránh tạo hai cấu hình repository cạnh tranh.

## 7. Điều gì xảy ra khi response commit sớm?

Response commit sớm thường xuất hiện trong các luồng redirect, lỗi, streaming hoặc ghi nội dung trực tiếp. Hãy hiểu tác động với từng trường hợp.

### 7.1. Redirect sau khi cập nhật phiên

Đây là trường hợp phổ biến. Controller thay đổi phiên rồi trả redirect. Khi framework gọi sendRedirect, Spring Session lưu phiên trước khi response được commit. Trình duyệt nhận cookie và gửi nó trong request theo sau.

Nếu redirect được tạo trước khi controller cập nhật phiên, dữ liệu mới không thể tự xuất hiện trong request đích. Thứ tự thao tác nghiệp vụ vẫn quan trọng.

### 7.2. Gửi lỗi bằng sendError

Một filter hoặc servlet có thể gọi sendError để kết thúc request bằng mã lỗi. Trước khi response gốc được commit, Spring Session cần xử lý việc lưu phiên theo cơ chế commit. Vì vậy, thuộc tính phiên được thay đổi trước khi gửi lỗi có thể vẫn được lưu.

Không nên coi sendError là rollback phiên. Nếu một thao tác nghiệp vụ thất bại và ứng dụng không muốn giữ thay đổi phiên đã thực hiện trước đó, hãy chủ động khôi phục dữ liệu phiên hoặc thiết kế thao tác cập nhật theo hướng chỉ áp dụng sau khi nghiệp vụ thành công.

### 7.3. Streaming và flushBuffer

Với endpoint trả file lớn hoặc stream dữ liệu, ứng dụng có thể flush output để dữ liệu được gửi ngay. Sau khi response commit, header và cookie không còn dễ thay đổi. Vì vậy, hãy hoàn tất việc tạo hoặc cập nhật phiên trước khi bắt đầu stream hay flush response.

Không nên dùng session làm nơi cập nhật trạng thái liên tục trong một luồng streaming kéo dài. Nếu cần tiến độ xử lý, trạng thái tác vụ hoặc dữ liệu lớn, hãy dùng một kho trạng thái phù hợp và cung cấp API truy vấn riêng.

### 7.4. Exception và xử lý lỗi

Nếu controller ném exception, filter vẫn có thể đi qua logic hoàn tất request. Việc phiên được lưu hay bị loại bỏ còn phụ thuộc phiên có được tạo, có bị invalidate, response đã commit hay repository gặp lỗi. Exception không tự động rollback những thuộc tính phiên đã thay đổi.

Nếu exception được xử lý bởi @ControllerAdvice hoặc error page, response cuối cùng có thể commit qua một đường đi khác. Cần kiểm thử luồng lỗi thực tế, nhất là khi handler thay đổi phiên hoặc redirect sau lỗi.

## 8. Filter order và tích hợp với Spring Security

SessionRepositoryFilter phải chạy trước những filter hoặc thành phần cần truy cập HttpSession. Nếu Spring Security chạy trước bộ lọc Spring Session, Security có thể đọc hoặc tạo session qua cơ chế mặc định của container trước khi wrapper của Spring Session được áp dụng. Kết quả là trạng thái xác thực có thể không nằm trong repository chia sẻ như mong muốn.

Trong ứng dụng Spring Boot, cấu hình tự động thường đăng ký filter ở thứ tự phù hợp. Nếu tự đăng ký filter hoặc tùy chỉnh thứ tự, cần bảo đảm SessionRepositoryFilter đứng trước Spring Security filter chain và mọi filter cần dùng session.

Một số lưu ý:

- Không đăng ký SessionRepositoryFilter hai lần.
- Tránh tự tạo session trong filter chạy trước SessionRepositoryFilter.
- Nếu có filter tùy chỉnh đọc SecurityContext hoặc HttpSession, kiểm tra thứ tự của nó.
- Khi ứng dụng có nhiều FilterRegistrationBean, hãy xác nhận thứ tự cuối cùng trong Servlet container.
- Kiểm thử cả request đăng nhập, request đã xác thực và logout để phát hiện việc dùng nhầm session của container.

Thứ tự filter có thể khiến ứng dụng trông như đã đăng nhập trong một instance nhưng request ở instance khác lại mất trạng thái. Khi gặp hiện tượng đó, hãy kiểm tra cookie, repository và filter order trước khi kết luận dữ liệu Redis/JDBC bị mất.

## 9. Vô hiệu hóa phiên và cookie

Lưu phiên khi response commit không có nghĩa mọi phiên đều được lưu. Khi ứng dụng gọi session.invalidate(), phiên được đánh dấu không còn hợp lệ và repository cần xóa phiên theo hợp đồng của nó. Bộ lọc cũng cần tránh lưu lại một phiên đã bị vô hiệu hóa.

Ví dụ logout trong một ứng dụng Servlet:

~~~java
@PostMapping("/logout")
public String logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session != null) {
        session.invalidate();
    }

    return "redirect:/login";
}
~~~

Với Spring Security, nên sử dụng cơ chế logout của Spring Security để phối hợp xóa SecurityContext, invalidate session và xử lý cookie theo cấu hình. Không tự xây dựng một endpoint logout chỉ xóa cookie ở trình duyệt mà bỏ qua việc thu hồi phiên ở repository.

Khi phiên bị invalidate, response có thể cần xóa cookie session ID hoặc gửi cookie hết hạn theo cách cấu hình của ứng dụng. Xóa cookie phía client và xóa bản ghi phía server là hai thao tác riêng; cần xác nhận cả hai trong kiểm thử logout.

## 10. Trường hợp async và nhiều request đồng thời

Servlet async cho phép xử lý tiếp tục sau khi thread ban đầu kết thúc. Vòng đời response và thời điểm commit vì vậy phức tạp hơn request đồng bộ thông thường. Các thao tác session nên diễn ra trong phạm vi request/dispatch được hỗ trợ bởi bộ lọc và trước khi response commit. Tránh giữ đối tượng HttpSession rồi sửa tùy ý từ một background thread sau khi request đã hoàn tất.

Nếu cần xử lý nền, hãy truyền định danh nghiệp vụ hoặc định danh tác vụ vào worker, lưu tiến độ ở một kho phù hợp và để request mới đọc trạng thái đó. Nếu bắt buộc cập nhật session trong luồng async, cần xác minh cách filter được ánh xạ cho async dispatch, thời điểm hoàn tất response và cách repository xử lý cập nhật đồng thời.

Hai request đồng thời của cùng một trình duyệt có thể cùng tải một phiên rồi thay đổi những thuộc tính khác nhau. Không phải mọi repository đều khóa toàn bộ phiên trong suốt thời gian request. Hai lần lưu có thể xảy ra gần nhau; nếu cả hai ghi một bản snapshot chứa trạng thái cũ, một thay đổi có thể bị ghi đè.

Để giảm rủi ro:

- Tránh dùng một thuộc tính phiên như bộ đếm có nhiều request cập nhật đồng thời mà không có cơ chế đồng bộ.
- Không dựa vào session để thực hiện cập nhật tài chính hoặc nghiệp vụ cần tính nguyên tử.
- Dùng transaction, optimistic locking hoặc thao tác nguyên tử trong kho dữ liệu nghiệp vụ khi cần.
- Giữ dữ liệu session nhỏ và tránh lưu các đối tượng lớn, thay đổi thường xuyên.
- Kiểm thử bằng nhiều request song song trên cùng cookie, không chỉ kiểm tra từng request tuần tự.

## 11. Cách kiểm thử thời điểm lưu

Có thể tạo một endpoint thử nghiệm ghi một thuộc tính vào session và trả redirect. Sau đó gửi request tiếp theo bằng cookie nhận từ response redirect. Nếu repository được cấu hình đúng, request thứ hai đọc được giá trị mới.

Một bộ kiểm thử nên bao gồm:

1. Request đầu tiên tạo session và đặt một thuộc tính.
2. Xác nhận response có cookie session ID khi phiên mới được tạo.
3. Gửi request tiếp theo với cookie đó và đọc được giá trị đã lưu.
4. Gọi sendRedirect sau khi thay đổi session và kiểm tra dữ liệu ở endpoint đích.
5. Gọi sendError sau khi thay đổi session và xác nhận hành vi lưu phù hợp với chính sách ứng dụng.
6. Flush response trong một endpoint thử nghiệm, sau đó xác nhận cookie đã được thiết lập trước khi commit.
7. Thay đổi đối tượng mutable trong session mà không gọi setAttribute để kiểm tra SaveMode.
8. Gửi nhiều request đồng thời trên cùng session để phát hiện cập nhật bị ghi đè.
9. Logout, gửi lại cookie cũ và xác nhận phiên không còn được khôi phục.

Khi dùng MockMvc, cần nhớ một số hành vi commit của Servlet container có thể không hoàn toàn giống môi trường chạy thật. Với kiểm thử streaming, async, redirect hoặc filter order, kiểm thử tích hợp với embedded server giúp xác nhận hành vi sát thực tế hơn.

## 12. Checklist vận hành

| Câu hỏi | Kết quả mong đợi |
|---|---|
| SessionRepositoryFilter có chạy trước Spring Security không? | Các thành phần bảo mật đều dùng session do Spring Session quản lý |
| Session có được lưu khi response commit sớm không? | Thay đổi phiên và cookie cần thiết được xử lý trước khi response gốc commit |
| Session có được lưu khi filter chain kết thúc không? | Các thay đổi trong request được đồng bộ theo flush mode |
| FlushMode có phù hợp không? | ON_SAVE gom ghi tại điểm save; IMMEDIATE ghi sớm hơn theo hỗ trợ repository |
| SaveMode có phù hợp với kiểu đối tượng phiên không? | Các thay đổi thuộc tính cần thiết được phát hiện và lưu |
| Logout có xóa phiên phía server không? | Repository không còn khôi phục được phiên đã invalidate |
| Async và streaming có được kiểm thử không? | Không sửa session sau khi response hoặc request lifecycle đã kết thúc |
| Request đồng thời có được kiểm tra không? | Không có cập nhật quan trọng bị ghi đè âm thầm |

## Kết luận

Spring Session trong môi trường Servlet lưu phiên ở cuối quá trình xử lý request và có thể lưu sớm hơn ngay trước khi response được commit. Cơ chế này giúp dữ liệu phiên và cookie session ID được cập nhật trước khi redirect, sendError hoặc flush response gửi dữ liệu về client. FlushMode quyết định thời điểm ghi repository, còn SaveMode quyết định tập thuộc tính được lưu. Để hành vi ổn định, cần đặt SessionRepositoryFilter đúng thứ tự, thay đổi session trước khi response commit, xử lý invalidate đúng cách và kiểm thử các luồng redirect, lỗi, streaming, async cùng request đồng thời.
