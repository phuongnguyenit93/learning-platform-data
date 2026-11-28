# Phân biệt thời điểm lưu với phạm vi dữ liệu được lưu

Khi dùng Spring Session, việc ghi một phiên xuống Redis hoặc JDBC có hai câu hỏi độc lập:

1. **Khi nào** thay đổi được ghi xuống repository?
2. **Những thuộc tính nào** của phiên được đưa vào lần ghi đó?

Spring Session có hai nhóm chính sách tương ứng: FlushMode điều khiển thời điểm flush dữ liệu; SaveMode điều khiển phạm vi thuộc tính phiên được lưu. Hai chính sách phối hợp với nhau nhưng không thay thế nhau. Chọn đúng giúp giảm số lần I/O, tránh bỏ sót thay đổi trong đối tượng mutable và kiểm soát chi phí serialization khi ứng dụng chạy trên nhiều instance.

Bài học đặt trong bối cảnh ứng dụng Servlet dùng Spring Session với kho phiên chia sẻ như Redis hoặc JDBC. Ứng dụng vẫn thao tác qua HttpSession; Spring Session quản lý việc đồng bộ phiên với repository. Tên thuộc tính cấu hình và mức hỗ trợ có thể thay đổi theo phiên bản Spring Boot, Spring Session và repository, vì vậy cần đối chiếu phiên bản thực tế của dự án.

## 1. Hai câu hỏi khác nhau trong một lần lưu

Một phiên có thể chứa nhiều thuộc tính:

- Thông tin giỏ hàng.
- Tùy chọn giao diện hoặc ngôn ngữ.
- Trạng thái của quy trình nhiều bước.
- SecurityContext trong cấu hình Spring Security stateful.
- Một số metadata do Servlet/Spring Session quản lý như thời gian truy cập và thời hạn không hoạt động.

Giả sử controller đọc giỏ hàng, thêm sản phẩm rồi trả response. Spring Session cần xác định lúc nào ghi thay đổi và thuộc tính nào cần ghi. FlushMode trả lời câu hỏi về thời điểm. SaveMode trả lời câu hỏi về tập thuộc tính.

| Chính sách | Câu hỏi | Ví dụ |
|---|---|---|
| FlushMode | Khi nào đẩy thay đổi xuống repository? | Ghi ngay khi có thay đổi hay gom đến lúc request được lưu |
| SaveMode | Những thuộc tính nào cần được ghi trong lần save? | Chỉ thuộc tính được set, thuộc tính đã đọc hoặc toàn bộ thuộc tính |

Có thể hình dung như sau:

    Request thay đổi HttpSession
              |
              v
       Theo dõi thuộc tính
              |
              | SaveMode xác định phạm vi
              v
       Tập thuộc tính cần lưu
              |
              | FlushMode xác định thời điểm
              v
       SessionRepository
              |
              v
        Redis / JDBC

SaveMode không chọn kho dữ liệu và cũng không quyết định thời điểm ghi. FlushMode không quyết định thuộc tính nào được xem là đã thay đổi. Nếu nhầm hai khái niệm này, cấu hình có thể giảm số lần ghi nhưng vẫn lưu sai tập thuộc tính, hoặc theo dõi đúng thuộc tính nhưng tạo quá nhiều thao tác I/O.

## 2. FlushMode: thời điểm thay đổi được ghi

FlushMode quy định khi nào repository nhận các thay đổi của phiên. Hai chế độ thường gặp là ON_SAVE và IMMEDIATE.

| Chế độ | Hành vi | Đặc điểm |
|---|---|---|
| ON_SAVE | Gom thay đổi rồi ghi khi repository được yêu cầu save phiên | Thường giảm số lần ghi trong một request |
| IMMEDIATE | Đẩy thay đổi xuống repository sớm nhất có thể khi thay đổi được ghi nhận | Thay đổi có thể xuất hiện ở kho dữ liệu sớm hơn, đổi lại có thể tăng I/O |

### 2.1. ON_SAVE

Với ON_SAVE, Spring Session theo dõi thay đổi trong suốt request. Khi request hoàn tất hoặc response sắp commit, SessionRepositoryFilter gọi cơ chế lưu phiên và repository ghi các thay đổi được đánh dấu.

Ví dụ:

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

Trong luồng trên, ON_SAVE cho phép gom cập nhật phiên trong request. Trước khi redirect được commit, Spring Session lưu các thay đổi cần thiết và cập nhật session ID/cookie nếu có. Request GET tiếp theo có thể khôi phục giỏ hàng mới từ repository.

ON_SAVE thường là lựa chọn phù hợp cho request Servlet thông thường vì một request có thể gọi setAttribute nhiều lần. Việc gom thay đổi giúp giảm số lần ghi Redis hoặc JDBC. Tuy nhiên, dữ liệu chỉ được ghi khi điểm save được thực hiện; nếu tiến trình chết trước đó, các thay đổi chưa được flush có thể chưa tồn tại ở repository.

### 2.2. IMMEDIATE

Với IMMEDIATE, thay đổi được đẩy xuống repository sớm hơn thay vì chờ điểm save cuối request. Chế độ này có thể hữu ích nếu ứng dụng cần giảm khoảng thời gian mà thay đổi chỉ tồn tại trong trạng thái đang xử lý của request.

Đổi lại, một request cập nhật nhiều thuộc tính có thể tạo nhiều thao tác ghi hơn. Nếu mỗi thao tác gây serialization hoặc round trip mạng, chi phí có thể tăng rõ rệt.

IMMEDIATE không phải transaction bao trùm request. Nếu request cập nhật một thuộc tính, sau đó phát sinh lỗi nghiệp vụ, lần ghi đã thực hiện không tự động bị rollback chỉ vì response cuối cùng là lỗi. Ứng dụng cần tự thiết kế tính nhất quán cho các thao tác nghiệp vụ liên quan.

### 2.3. FlushMode không phải cam kết transaction

Không nên hiểu IMMEDIATE là bảo đảm mọi thay đổi đã được commit bền vững vào mọi replica hoặc mọi node ngay tức thì. Nó chỉ điều khiển thời điểm Spring Session đẩy thay đổi qua repository theo khả năng của implementation.

Tương tự, ON_SAVE không có nghĩa toàn bộ request và mọi thao tác cơ sở dữ liệu nằm trong cùng một transaction. Session repository có thể dùng cơ chế kết nối và transaction riêng. Nếu nghiệp vụ cần cập nhật đơn hàng, số dư hoặc tồn kho nguyên tử, hãy dùng transaction và mô hình dữ liệu nghiệp vụ phù hợp thay vì dựa vào FlushMode.

## 3. SaveMode: phạm vi thuộc tính được ghi

SaveMode quyết định tập thuộc tính session được đưa vào thao tác lưu. Các chế độ phổ biến là ON_SET_ATTRIBUTE, ON_GET_ATTRIBUTE và ALWAYS.

| Chế độ | Thuộc tính được đưa vào lần save | Khi nào hữu ích |
|---|---|---|
| ON_SET_ATTRIBUTE | Thuộc tính được đặt hoặc cập nhật qua setAttribute trong request | Khi ứng dụng thay thế/đặt lại thuộc tính rõ ràng |
| ON_GET_ATTRIBUTE | Thuộc tính đã được đọc qua getAttribute và thuộc tính được đặt | Khi ứng dụng đọc rồi sửa đối tượng mutable trong phiên |
| ALWAYS | Tất cả thuộc tính của phiên | Khi cần cách lưu đơn giản, ưu tiên tính bao quát hơn chi phí ghi |

SaveMode chủ yếu liên quan đến các thuộc tính của phiên. Nó không quyết định một phiên có tồn tại hay bị invalidate, cũng không thay thế việc lưu metadata phiên như thời gian truy cập hoặc thời hạn. Các thao tác tạo, xóa và cập nhật vòng đời phiên vẫn được repository xử lý theo hợp đồng riêng.

Một điểm dễ nhầm: ON_SET_ATTRIBUTE không có nghĩa những thuộc tính khác trong phiên bị xóa. Nó có nghĩa lần lưu hiện tại chỉ cần ghi các thuộc tính được đánh dấu theo chính sách đó. Những thuộc tính đã lưu từ request trước vẫn tồn tại trong repository nếu không bị xóa hoặc thay thế.

## 4. Vì sao ON_SET_ATTRIBUTE cần chú ý với đối tượng mutable?

Giả sử phiên chứa một đối tượng Cart. Controller đọc đối tượng đó rồi sửa trực tiếp danh sách sản phẩm:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add("BOOK-02");
~~~

Lời gọi getAttribute trả về tham chiếu đến đối tượng Cart trong phiên. Lệnh cart.add() thay đổi trạng thái bên trong đối tượng, nhưng không gọi HttpSession.setAttribute(). Nếu SaveMode chỉ theo dõi các thuộc tính được đặt, repository có thể không đánh dấu thuộc tính cart là cần ghi.

Kết quả là request hiện tại nhìn thấy giỏ hàng mới trong bộ nhớ, nhưng request tiếp theo tải từ Redis/JDBC có thể vẫn thấy dữ liệu cũ.

Có hai cách xử lý phổ biến.

**Cách 1: đặt lại thuộc tính sau khi sửa.**

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.add("BOOK-02");
session.setAttribute("cart", cart);
~~~

Việc gọi setAttribute báo cho Spring Session biết thuộc tính đã thay đổi. Đây thường là cách dễ đọc và dễ kiểm tra nhất khi dùng ON_SET_ATTRIBUTE.

**Cách 2: dùng ON_GET_ATTRIBUTE nếu mô hình truy cập phù hợp.**

Với ON_GET_ATTRIBUTE, thuộc tính được đọc qua getAttribute cũng được đánh dấu để ghi trong lần save. Vì vậy, thay đổi bên trong đối tượng mutable được đọc trong request có thể được lưu dù code không gọi setAttribute lần nữa.

Cách này có thể phù hợp với codebase có nhiều thao tác đọc rồi sửa đối tượng trong session. Tuy nhiên, nếu request chỉ đọc một thuộc tính mà không sửa nó, thuộc tính vẫn có thể được ghi lại, làm tăng serialization và I/O. Vì vậy, ON_GET_ATTRIBUTE cần được chọn dựa trên cách ứng dụng sử dụng session, không phải mặc định xem là an toàn hơn.

## 5. ALWAYS và chi phí ghi toàn bộ thuộc tính

ALWAYS yêu cầu repository ghi tất cả thuộc tính phiên trong lần save. Điều này có thể hữu ích khi ứng dụng có mô hình cập nhật khó theo dõi hoặc muốn ưu tiên đơn giản hóa việc phát hiện thay đổi.

Ví dụ một phiên có:

- Cart gồm nhiều dòng sản phẩm.
- UserPreferences gồm các tùy chọn giao diện.
- WizardState lưu tiến độ biểu mẫu.
- SecurityContext lưu Authentication.

Nếu mỗi request chỉ thay đổi WizardState nhưng ALWAYS ghi lại tất cả, repository có thể phải serialize cả Cart, UserPreferences và SecurityContext. Với đối tượng lớn hoặc có serialization tốn kém, điều này làm tăng CPU, băng thông và độ trễ.

ALWAYS cũng không giải quyết các lỗi thiết kế như lưu đối tượng không phù hợp vào session, cập nhật đồng thời bị ghi đè hoặc dùng session làm kho dữ liệu nghiệp vụ lâu dài. Nó chỉ mở rộng tập thuộc tính được ghi trong mỗi lần save.

Một nguyên tắc thực tế là giữ session nhỏ, chỉ lưu dữ liệu cần thiết giữa các request và chọn SaveMode phù hợp với cách cập nhật thuộc tính.

## 6. Kết hợp FlushMode và SaveMode

Hai chính sách phối hợp theo hai trục độc lập. Ví dụ:

| FlushMode | SaveMode | Ý nghĩa |
|---|---|---|
| ON_SAVE | ON_SET_ATTRIBUTE | Gom đến điểm save, chỉ ghi thuộc tính được set/cập nhật |
| ON_SAVE | ON_GET_ATTRIBUTE | Gom đến điểm save, ghi cả thuộc tính đã được đọc |
| ON_SAVE | ALWAYS | Gom đến điểm save, ghi toàn bộ thuộc tính |
| IMMEDIATE | ON_SET_ATTRIBUTE | Ghi sớm các thay đổi thuộc tính được đánh dấu |
| IMMEDIATE | ON_GET_ATTRIBUTE | Ghi sớm theo các thay đổi được đánh dấu, kể cả thuộc tính đã đọc |
| IMMEDIATE | ALWAYS | Phạm vi dữ liệu rộng, thời điểm ghi sớm; cần cân nhắc kỹ chi phí |

Bảng thể hiện nguyên tắc kết hợp; hành vi chi tiết còn phụ thuộc repository và phiên bản. Đặc biệt, IMMEDIATE không có nghĩa repository luôn ghi toàn bộ session sau mọi lần đọc. SaveMode vẫn là chính sách xác định thuộc tính nào được đánh dấu cho thao tác lưu.

Một lựa chọn thường hợp lý cho ứng dụng web là ON_SAVE kết hợp ON_SET_ATTRIBUTE, đồng thời code gọi setAttribute sau khi sửa đối tượng mutable. Cấu hình này làm rõ điểm ghi và làm rõ thuộc tính thay đổi. Nếu codebase có nhiều đoạn đọc rồi sửa đối tượng mà không set lại, có thể cân nhắc ON_GET_ATTRIBUTE hoặc refactor cách cập nhật để đánh dấu thay đổi rõ ràng.

## 7. Ví dụ cấu hình Redis trong Spring Boot

Với module Spring Session Redis, cấu hình có thể đặt trong application.yml:

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

Trong ví dụ:

- store-type chọn repository Redis.
- timeout đặt thời gian không hoạt động tối đa của phiên.
- flush-mode chọn thời điểm ghi.
- save-mode chọn tập thuộc tính được lưu.
- namespace phân vùng key của ứng dụng trong Redis.

Tên prefix và các giá trị hợp lệ phụ thuộc phiên bản Spring Boot/Spring Session. Hãy kiểm tra metadata cấu hình và tài liệu của phiên bản dự án trước khi áp dụng.

Nếu dùng cấu hình Java thủ công, các thuộc tính tương ứng có thể được thiết lập qua cấu hình repository hoặc annotation bật repository, tùy phiên bản:

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

Nếu ứng dụng đang dùng auto-configuration của Spring Boot, hãy ưu tiên thuộc tính Boot đã hỗ trợ. Tránh vừa bật repository thủ công vừa để auto-configuration tạo một cấu hình cạnh tranh.

Với JDBC, hãy xác minh repository và phiên bản đang dùng hỗ trợ những chính sách nào, cũng như prefix thuộc tính tương ứng. Không sao chép cấu hình spring.session.redis.* sang JDBC. Dù repository khác nhau, cần giữ rõ hai câu hỏi về thời điểm lưu và phạm vi thuộc tính được lưu.

## 8. Những gì SaveMode không kiểm soát

SaveMode chỉ là một phần của cơ chế ghi session. Nó không phải bộ lọc dữ liệu tổng quát và không quyết định dữ liệu nào được phép tồn tại trong ứng dụng.

Các trường hợp sau nằm ngoài ý nghĩa trực tiếp của SaveMode:

- Dữ liệu trong database nghiệp vụ như đơn hàng hoặc hồ sơ.
- Cache độc lập không lưu trong HttpSession.
- File upload hoặc dữ liệu trên object storage.
- Việc invalidate session và thu hồi session ID.
- Chính sách xác thực và phân quyền.
- Transaction nghiệp vụ giữa nhiều repository.
- Quy tắc retention hoặc xóa dữ liệu theo yêu cầu pháp lý.

Ví dụ, gọi session.invalidate() yêu cầu repository xóa phiên theo hợp đồng vòng đời. Đây không phải thao tác chỉ lưu một tập thuộc tính theo SaveMode. Tương tự, thay đổi TTL hoặc last accessed time thuộc metadata vòng đời phiên và được xử lý theo cơ chế repository.

Không nên cố dùng SaveMode để bảo đảm một thuộc tính nhạy cảm bị loại bỏ. Nếu cần xóa dữ liệu, hãy gọi removeAttribute hoặc invalidate session theo đúng nghiệp vụ, sau đó kiểm thử rằng repository đã phản ánh việc xóa.

## 9. Thay đổi thuộc tính, xóa thuộc tính và đối tượng lồng nhau

Cần hiểu rõ ba kiểu thao tác:

~~~java
// Đặt một thuộc tính mới hoặc thay thế giá trị
session.setAttribute("theme", "dark");

// Đọc một thuộc tính
Object cart = session.getAttribute("cart");

// Xóa một thuộc tính
session.removeAttribute("wizardState");
~~~

setAttribute và removeAttribute là những thao tác thay đổi rõ ràng mà Spring Session có thể theo dõi. getAttribute chỉ là đọc; với ON_SET_ATTRIBUTE, đọc đơn thuần không làm thuộc tính trở thành thuộc tính cần ghi. Với ON_GET_ATTRIBUTE, thuộc tính đã đọc được đánh dấu theo chính sách.

Đối tượng lồng nhau cũng cần được lưu ý. Nếu session lưu một Map chứa Cart, rồi code thay đổi một list bên trong Map mà không gọi setAttribute, thay đổi có thể không được phát hiện theo ON_SET_ATTRIBUTE. Cách an toàn là tạo trạng thái mới hoặc đặt lại thuộc tính sau khi sửa:

~~~java
@SuppressWarnings("unchecked")
Map<String, Object> state =
        (Map<String, Object>) session.getAttribute("state");

state.put("step", "PAYMENT");
session.setAttribute("state", state);
~~~

Trong code nghiệp vụ, nên đóng gói thao tác cập nhật vào service thay vì để nhiều controller sửa đối tượng mutable tùy ý. Điều này giúp xác định nơi nào cần đánh dấu thuộc tính đã thay đổi và dễ kiểm thử hơn.

## 10. Ảnh hưởng đến hiệu năng và khả năng mở rộng

Chính sách ghi ảnh hưởng đến CPU, mạng và tải của kho dữ liệu.

| Lựa chọn | Chi phí có thể phát sinh | Rủi ro cần quan sát |
|---|---|---|
| ON_SAVE | Ít lần ghi hơn trong một request thông thường | Thay đổi chưa flush nếu tiến trình dừng trước điểm save |
| IMMEDIATE | Nhiều lần round trip hơn khi có nhiều thay đổi | Tăng tải Redis/JDBC và có trạng thái trung gian |
| ON_SET_ATTRIBUTE | Chỉ serialize thuộc tính được đánh dấu | Bỏ sót sửa đổi bên trong đối tượng nếu không set lại |
| ON_GET_ATTRIBUTE | Nhiều thuộc tính được đọc có thể bị ghi lại | Tăng serialization dù một số request chỉ đọc |
| ALWAYS | Có thể serialize toàn bộ thuộc tính phiên | Tăng CPU, băng thông và độ trễ khi session lớn |

Để đánh giá, không chỉ đo số lệnh ghi. Hãy quan sát kích thước session, thời gian serialize/deserialize, độ trễ repository, số lần ghi trên mỗi request và tỷ lệ lỗi lưu. Với JDBC, cần xem thêm tải connection pool, transaction và truy vấn cập nhật. Với Redis, cần xem latency, network throughput và mức tiêu thụ bộ nhớ.

Không nên tối ưu bằng cách chọn chế độ ít ghi nhất rồi bỏ qua tính đúng đắn. Nếu một thay đổi quan trọng không được lưu, request kế tiếp có thể xử lý trên trạng thái cũ. Ngược lại, ghi mọi thuộc tính trong mọi request có thể làm kho phiên thành điểm nghẽn.

## 11. Request đồng thời và giới hạn của chính sách ghi

Giả sử hai request cùng dùng một session. Request A tải giỏ hàng có hai sản phẩm. Request B cũng tải cùng snapshot. A thêm sản phẩm thứ ba rồi lưu; B thay đổi tùy chọn giao diện rồi lưu snapshot mà nó đang giữ.

Dù SaveMode là ON_SET_ATTRIBUTE hay ALWAYS, việc ghi các thuộc tính vẫn có thể gặp cạnh tranh. Nếu cả hai request lưu một đối tượng session hoặc một thuộc tính có trạng thái cũ, cập nhật của request sau có thể ghi đè thay đổi trước. FlushMode IMMEDIATE cũng không tự biến chuỗi thao tác thành cập nhật nguyên tử.

Để xử lý:

- Tránh dùng một thuộc tính session làm bộ đếm hoặc trạng thái có nhiều request đồng thời sửa.
- Giữ các cập nhật trong session nhỏ và ít tranh chấp.
- Dùng câu lệnh cập nhật nguyên tử, transaction hoặc optimistic locking trong database nghiệp vụ khi cần.
- Với thao tác quan trọng, đọc trạng thái mới nhất trong service và kiểm tra điều kiện trước khi ghi.
- Kiểm thử nhiều request song song cùng cookie, bao gồm trường hợp sửa cùng thuộc tính và hai thuộc tính khác nhau.

Session phù hợp để giữ ngữ cảnh tương tác ngắn hạn. Nó không thay thế kho dữ liệu giao dịch cần bảo đảm tính nguyên tử hoặc nhất quán mạnh.

## 12. Ví dụ kiểm tra khác biệt giữa hai chính sách

Có thể dùng một bài kiểm thử đơn giản để quan sát SaveMode:

~~~java
@Test
void updatesMutableAttribute() throws Exception {
    MockHttpSession session = new MockHttpSession();
    session.setAttribute("cart", new Cart(List.of("BOOK-01")));

    mockMvc.perform(post("/cart/add")
            .session(session)
            .param("sku", "BOOK-02"))
        .andExpect(status().isOk());

    mockMvc.perform(get("/cart")
            .session(session))
        .andExpect(jsonPath("$.items.length()").value(2));
}
~~~

Đây là minh họa cho logic kiểm thử; MockHttpSession của Spring Test không tự xác minh Redis/JDBC repository thực tế. Để kiểm tra SaveMode và FlushMode, cần chạy ứng dụng với Spring Session repository tương ứng và gửi request qua SessionRepositoryFilter.

Một bộ kiểm thử tích hợp nên có:

1. Tạo phiên và lưu thuộc tính mới bằng setAttribute.
2. Gửi request sau để xác nhận thuộc tính tồn tại.
3. Đọc rồi sửa một đối tượng mutable mà không gọi setAttribute, so sánh hành vi ON_SET_ATTRIBUTE và ON_GET_ATTRIBUTE.
4. Sửa cùng đối tượng rồi gọi setAttribute, xác nhận ON_SET_ATTRIBUTE lưu được thay đổi.
5. Xóa thuộc tính bằng removeAttribute và xác nhận request sau không còn giá trị đó.
6. Với ALWAYS, kiểm tra thuộc tính không được đọc trong request nhưng vẫn được lưu theo chính sách.
7. Với ON_SAVE, xác nhận thay đổi xuất hiện sau điểm save của request.
8. Với IMMEDIATE, quan sát thời điểm ghi theo repository và xác nhận không nhầm nó với transaction nghiệp vụ.
9. Gửi redirect sau khi sửa session để xác nhận phiên được lưu trước response commit.
10. Gửi nhiều request đồng thời để kiểm tra cập nhật bị ghi đè.

Đối với Redis/JDBC, dùng kho dữ liệu thật hoặc môi trường tích hợp tương thích để xác nhận serialization, TTL, flush và save behavior. Một unit test với mock không chứng minh repository đã ghi đúng dữ liệu.

## 13. Chọn chính sách theo cách ứng dụng sử dụng session

Có thể dùng các gợi ý sau làm điểm xuất phát:

| Cách ứng dụng cập nhật session | Gợi ý |
|---|---|
| Luôn gọi setAttribute sau khi thay đổi | ON_SET_ATTRIBUTE thường phù hợp |
| Thường đọc rồi sửa đối tượng mutable mà không set lại | Cân nhắc ON_GET_ATTRIBUTE hoặc refactor để set lại |
| Muốn mọi thuộc tính được ghi trong mỗi lần save | ALWAYS, sau khi đo chi phí |
| Request có nhiều lần thay đổi session và muốn gom ghi | ON_SAVE |
| Có lý do rõ ràng cần đẩy thay đổi sớm hơn | Cân nhắc IMMEDIATE và kiểm tra tải kho dữ liệu |
| Session lớn, request chỉ sửa một vài thuộc tính | ON_SET_ATTRIBUTE kết hợp ON_SAVE thường giảm công việc ghi |

Đừng chọn chính sách chỉ dựa trên tên chế độ. Hãy kiểm tra pattern truy cập thực tế: controller có sửa object mutable không, service có thay thế thuộc tính không, session có SecurityContext hoặc object lớn không, và request có thể kết thúc bằng redirect/error/streaming không.

## 14. Quy trình cấu hình và vận hành

Một quy trình triển khai an toàn có thể gồm:

1. Xác định repository và phiên bản Spring Session đang dùng.
2. Liệt kê các thuộc tính thực sự cần lưu trong HttpSession.
3. Kiểm tra code có gọi setAttribute sau khi sửa object mutable không.
4. Chọn SaveMode theo cách thuộc tính được truy cập và cập nhật.
5. Chọn FlushMode theo thời điểm ghi mong muốn và chi phí I/O.
6. Xác nhận cấu hình được nạp đúng profile và không bị bean tùy chỉnh thay thế.
7. Kiểm thử request bình thường, redirect, lỗi, logout và request đồng thời.
8. Đo kích thước session, số lần ghi, latency và serialization cost.
9. Khi nâng cấp Spring Boot/Spring Session, xác minh lại giá trị mặc định và thuộc tính cấu hình.

Trong hệ thống nhiều instance, các node cần dùng cấu hình tương thích về repository, serializer, namespace và chính sách ghi. Nếu một instance dùng SaveMode khác hoặc phiên bản khác, các request được định tuyến luân phiên có thể có hành vi lưu không nhất quán. Quản lý cấu hình tập trung và rollout phiên bản có kiểm soát giúp tránh tình trạng đó.

## Kết luận

FlushMode và SaveMode điều khiển hai khía cạnh riêng của việc lưu phiên. FlushMode quyết định thời điểm thay đổi được đẩy xuống repository; SaveMode quyết định tập thuộc tính được đưa vào lần lưu. ON_SAVE thường gom ghi đến cuối request hoặc trước response commit, còn IMMEDIATE đẩy thay đổi sớm hơn. ON_SET_ATTRIBUTE theo dõi thuộc tính được đặt, ON_GET_ATTRIBUTE mở rộng sang thuộc tính được đọc, và ALWAYS ghi toàn bộ thuộc tính. Hãy chọn chúng dựa trên cách ứng dụng cập nhật session, đặc biệt là đối tượng mutable, rồi xác minh bằng kiểm thử tích hợp với Redis/JDBC và request đồng thời.
