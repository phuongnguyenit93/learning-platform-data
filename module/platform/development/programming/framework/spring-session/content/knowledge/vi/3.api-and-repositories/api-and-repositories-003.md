# Tạo đối tượng phiên khác với lưu phiên vào kho

Trong Spring Session, tạo một đối tượng phiên và lưu phiên vào kho dữ liệu là hai thao tác có ý nghĩa khác nhau. Lệnh tạo phiên cấp phát một đối tượng Session trong tiến trình đang chạy. Lệnh lưu phiên ghi trạng thái của đối tượng đó vào repository để lần đọc sau có thể tìm thấy, kể cả khi yêu cầu được xử lý bởi một instance ứng dụng khác.

Sự phân biệt này quan trọng khi làm việc trực tiếp với API SessionRepository. Với ứng dụng Servlet thông thường, SessionRepositoryFilter tích hợp Spring Session với HttpSession và tự quản lý phần lớn vòng đời lưu phiên trong quá trình xử lý yêu cầu. Khi gọi repository trực tiếp, mã ứng dụng phải chủ động gọi save sau khi tạo hoặc thay đổi phiên.

## 1. Ba khái niệm cần phân biệt

Spring Session tách mô hình phiên, thao tác truy cập phiên và nơi lưu dữ liệu thành các phần riêng:

- **Session:** mô tả dữ liệu và trạng thái của một phiên, gồm mã phiên, thời điểm truy cập gần nhất, thời hạn không hoạt động và các thuộc tính như userId hoặc cartId. Đây là đối tượng mà mã ứng dụng đọc và cập nhật.
- **SessionRepository<S extends Session>:** cung cấp các thao tác tạo, tìm, lưu và xóa phiên. Repository là ranh giới giữa đối tượng phiên trong ứng dụng và cơ chế lưu trữ.
- **Kho dữ liệu:** nơi repository ghi dữ liệu phiên, chẳng hạn Redis hoặc các bảng trong cơ sở dữ liệu quan hệ khi dùng Spring Session JDBC.

Một đối tượng Session đang tồn tại trong heap của Instance A không tự động xuất hiện trong heap của Instance B. Ngay cả khi hai instance dùng chung Redis, mỗi instance vẫn làm việc với đối tượng Java của riêng mình. Repository chuyển trạng thái qua kho dữ liệu; nó không chia sẻ cùng một tham chiếu Java giữa các tiến trình.

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Đối tượng Session | Giữ trạng thái phiên trong lần xử lý hiện tại | Mã phiên, userId, cartId |
| SessionRepository | Tạo, tìm, lưu và xóa trạng thái phiên | createSession(), findById(), save() |
| Kho dữ liệu | Giữ dữ liệu để các lần xử lý sau có thể truy cập | Redis, JDBC |

## 2. Vòng đời của một phiên

Một phiên được quản lý bởi repository thường trải qua các bước: tạo đối tượng, đặt thuộc tính, lưu, đọc lại, cập nhật và cuối cùng xóa hoặc hết hạn.

~~~mermaid
flowchart TD
    A["createSession()"] --> B["Đối tượng Session trong bộ nhớ"]
    B --> C["Đặt thuộc tính và thời hạn"]
    C --> D["save(session)"]
    D --> E[("Kho dữ liệu phiên")]
    E --> F["findById(sessionId)"]
    F --> G["Đối tượng phiên được nạp cho lần xử lý mới"]
    G --> H["Cập nhật thuộc tính"]
    H --> D
    E --> I["deleteById(sessionId) hoặc hết TTL"]
~~~

Điểm quyết định là bước save. Trước khi lưu, đối tượng mới chỉ là trạng thái trong bộ nhớ của tiến trình hiện tại. Sau khi lưu thành công, repository đã ghi trạng thái phiên vào kho dữ liệu theo cơ chế của implementation đang dùng. Một instance khác có thể gọi findById với cùng mã phiên để tải trạng thái đã lưu.

Việc lưu thành công không có nghĩa mọi instance cùng nhận được một đối tượng Java đang sống. Instance B đọc phiên sẽ nhận một đối tượng riêng được tạo từ dữ liệu trong repository. Vì thế, sau khi thay đổi đối tượng, ứng dụng vẫn cần lưu lại để thay đổi có thể được những lần đọc sau nhìn thấy.

## 3. API cốt lõi của SessionRepository

SessionRepository là API trung tâm để thao tác với phiên. Kiểu S là kiểu cụ thể triển khai Session; nó có thể khác nhau tùy repository đang được cấu hình.

| Phương thức | Ý nghĩa | Kết quả thường gặp |
| --- | --- | --- |
| createSession() | Tạo đối tượng phiên mới và chuẩn bị mã phiên | Trả về một đối tượng S |
| findById(id) | Tìm phiên đã được lưu theo mã phiên | Trả về S, hoặc null nếu không tìm thấy |
| save(session) | Lưu phiên mới hoặc trạng thái cập nhật | Ghi trạng thái qua repository |
| deleteById(id) | Xóa phiên theo mã | Phiên không còn được truy xuất như một phiên đang tồn tại |

Tên và kiểu tham số của các API trên thể hiện rõ trách nhiệm. createSession() tạo đối tượng; save() thực hiện thao tác lưu. Không nên suy ra rằng gọi createSession() đồng nghĩa repository đã có bản ghi phiên có thể đọc lại.

### Tạo đối tượng phiên

createSession() tạo một đối tượng phiên mới. Repository thường chuẩn bị một session ID và các giá trị mặc định như thời điểm truy cập hoặc khoảng thời gian không hoạt động. Ở bước này, ứng dụng có thể đặt thuộc tính lên đối tượng:

~~~java
var session = repository.createSession();
session.setAttribute("userId", "user-42");
session.setAttribute("cartId", "cart-105");
~~~

Đoạn mã trên mới tạo và thay đổi đối tượng trong bộ nhớ. Nếu ứng dụng kết thúc xử lý mà không gọi save, không có cam kết rằng một lần findById tiếp theo sẽ tìm thấy phiên đó.

### Lưu phiên

Sau khi chuẩn bị dữ liệu cần lưu, gọi save(session):

~~~java
repository.save(session);
String sessionId = session.getId();
~~~

Khi lời gọi save hoàn tất thành công, repository đã thực hiện thao tác ghi theo implementation của nó. Nếu thao tác gặp lỗi kết nối, lỗi tuần tự hóa hoặc lỗi cơ sở dữ liệu, ứng dụng cần xử lý ngoại lệ phù hợp. Không nên coi session ID là một phiên đã sẵn sàng sử dụng nếu thao tác lưu chưa thành công.

### Tìm và cập nhật phiên

Để tiếp tục làm việc với phiên đã lưu, dùng findById:

~~~java
var session = repository.findById(sessionId);
if (session == null) {
    throw new IllegalStateException("Session not found");
}

session.setAttribute("lastAction", "ADD_ITEM");
repository.save(session);
~~~

findById tải trạng thái phiên từ repository vào đối tượng mà lần xử lý hiện tại sử dụng. Thay đổi thuộc tính trên đối tượng vừa tải không tự động đồng nghĩa với việc kho dữ liệu đã thay đổi. Gọi save sau khi cập nhật để ghi trạng thái mới.

### Xóa phiên

Khi không còn cần phiên, có thể xóa bằng deleteById:

~~~java
repository.deleteById(sessionId);
~~~

Trong ứng dụng Servlet, thao tác đăng xuất thường được biểu diễn bằng HttpSession.invalidate(). Khi dùng Spring Session filter, thao tác này được chuyển thành việc xóa phiên qua repository và xử lý cookie tương ứng. Nếu thao tác trực tiếp với repository, ứng dụng tự chịu trách nhiệm về giao thức nhận diện phiên và việc thông báo cho client rằng phiên không còn hợp lệ.

## 4. Ví dụ dùng SessionRepository trực tiếp

Ví dụ sau minh họa một hàm generic có thể làm việc với các implementation SessionRepository khác nhau. S được suy ra từ kiểu repository thực tế được truyền vào:

~~~java
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;

public final class CartSessionOperations {

    private CartSessionOperations() {
    }

    public static <S extends Session> String create(
            SessionRepository<S> repository,
            String userId,
            String cartId) {

        S session = repository.createSession();
        session.setAttribute("userId", userId);
        session.setAttribute("cartId", cartId);

        // Ghi phiên vào kho trước khi dùng session ID ở nơi khác.
        repository.save(session);
        return session.getId();
    }

    public static <S extends Session> boolean updateCart(
            SessionRepository<S> repository,
            String sessionId,
            String newCartId) {

        S session = repository.findById(sessionId);
        if (session == null) {
            return false;
        }

        session.setAttribute("cartId", newCartId);
        repository.save(session);
        return true;
    }

    public static <S extends Session> void remove(
            SessionRepository<S> repository,
            String sessionId) {

        repository.deleteById(sessionId);
    }
}
~~~

Đây là ví dụ ở mức API repository. Ứng dụng cần cung cấp một bean repository đã được cấu hình và kiểu S tương ứng với implementation đó. Với Redis, kiểu phiên cụ thể do repository Redis cung cấp; với JDBC, kiểu phiên do repository JDBC cung cấp. Không nên ép kiểu mọi implementation về MapSession nếu kiểu thực tế không phải MapSession.

Trình tự trong hàm create có chủ ý: tạo đối tượng, đặt các thuộc tính cần thiết, lưu thành công rồi mới trả session ID. Hàm updateCart cũng đọc phiên hiện có, kiểm tra trường hợp không tìm thấy, cập nhật và lưu lại. Hàm remove chỉ thao tác với repository; nếu ứng dụng dùng cookie hoặc một cơ chế token riêng, lớp xử lý HTTP cần phối hợp để client không tiếp tục dùng một mã phiên đã bị xóa.

## 5. Spring Session tích hợp với HttpSession như thế nào?

Phần lớn ứng dụng Spring MVC hoặc Spring Boot Servlet không cần gọi SessionRepository trực tiếp. Spring Session cung cấp SessionRepositoryFilter, một Servlet filter bọc request và response để tích hợp repository với API HttpSession.

Controller có thể dùng API Servlet quen thuộc:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CartController {

    @PostMapping("/cart/select")
    String selectCart(HttpServletRequest request) {
        HttpSession session = request.getSession();
        session.setAttribute("cartId", "cart-105");
        return "Cart selected";
    }
}
~~~

Khi SessionRepositoryFilter đứng trong chuỗi filter và được cấu hình với repository, request wrapper chuyển các thao tác HttpSession sang đối tượng Session mà Spring Session quản lý. Ở mức khái niệm, luồng xử lý như sau:

1. Trình duyệt gửi cookie chứa session ID nếu đã có phiên.
2. Filter đọc session ID và dùng repository để tìm phiên tương ứng.
3. Nếu mã ứng dụng gọi request.getSession() mà chưa có phiên, wrapper yêu cầu repository tạo đối tượng phiên mới.
4. Controller đọc hoặc thay đổi thuộc tính thông qua HttpSession.
5. Filter lưu trạng thái phiên theo cơ chế flush đã cấu hình và xử lý cookie phiên trong response.

Do đó, request.getSession() có thể làm xuất hiện một đối tượng phiên trong lần xử lý hiện tại mà không có nghĩa controller đã trực tiếp ghi dữ liệu vào Redis ngay tại dòng lệnh đó. Filter chịu trách nhiệm quản lý việc lưu phiên trong vòng đời request/response.

### getSession() và getSession(false)

Hai cách gọi này có ý nghĩa khác nhau:

- request.getSession() trả về phiên hiện tại; nếu chưa có phiên hợp lệ, container hoặc wrapper có thể tạo phiên mới.
- request.getSession(false) chỉ trả về phiên hiện có; nếu không có phiên thì trả về null, không tạo phiên mới.

Khi chỉ muốn kiểm tra trạng thái đăng nhập hoặc đọc một thuộc tính tùy chọn, getSession(false) giúp tránh tạo phiên mới không cần thiết. Nếu mọi request đọc trạng thái đều vô tình tạo session, ứng dụng có thể phát sinh nhiều phiên rỗng và tăng tải cho kho dữ liệu.

### Đăng xuất qua HttpSession

Với Servlet API, đăng xuất thường gọi:

~~~java
void logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session != null) {
        session.invalidate();
    }
}
~~~

Khi Spring Session quản lý HttpSession, filter chuyển thao tác invalidate thành việc xóa phiên qua repository. Cookie phiên trong response cũng cần được xử lý để trình duyệt không tiếp tục dùng mã cũ. Trong ứng dụng dùng Spring Security, nên tích hợp với cơ chế logout của Spring Security để việc xóa context xác thực, vô hiệu hóa session và xử lý cookie đi cùng nhau.

## 6. Thời điểm lưu: flush mode và save mode

Khi dùng trực tiếp repository, thời điểm ghi rõ ràng là lúc mã gọi save(session). Khi dùng HttpSession qua SessionRepositoryFilter, filter quyết định thời điểm gọi repository dựa trên cấu hình lưu.

Hai cấu hình thường được nhắc đến là FlushMode và SaveMode. Chúng giải quyết hai câu hỏi khác nhau:

| Cấu hình | Câu hỏi | Ý nghĩa |
| --- | --- | --- |
| FlushMode | Khi nào đẩy thay đổi xuống repository? | ON_SAVE gom thay đổi đến lúc lưu; IMMEDIATE cố gắng lưu thay đổi ngay khi có thể |
| SaveMode | Thuộc tính nào cần được lưu? | Kiểm soát cách phát hiện và ghi thuộc tính phiên, ví dụ ON_SET_ATTRIBUTE, ALWAYS hoặc ON_GET_ATTRIBUTE |

Với ON_SAVE, thay đổi có thể nằm trong đối tượng phiên trong suốt quá trình xử lý request và được ghi khi filter lưu phiên, thường gắn với thời điểm response được commit. IMMEDIATE giảm khoảng thời gian thay đổi chưa được ghi nhưng có thể làm tăng số lần truy cập kho dữ liệu. Hành vi chi tiết còn phụ thuộc repository và cách filter quản lý request.

SaveMode không thay thế FlushMode. Chọn ON_SET_ATTRIBUTE có nghĩa Spring Session theo dõi việc gọi setAttribute để xác định thuộc tính cần lưu; nó không có nghĩa dữ liệu tự động được ghi ngay lập tức. Ngược lại, chọn IMMEDIATE không làm cho mọi thao tác đọc-sửa-ghi nhiều bước trở thành giao dịch nguyên tử.

Nếu mã ứng dụng thay đổi một đối tượng mutable đã nằm trong session mà không gọi lại setAttribute, repository có thể không phát hiện thay đổi trong một số chế độ lưu. Ví dụ, lấy một List, thêm phần tử trực tiếp rồi không gán lại thuộc tính có thể không được nhận diện như một lần cập nhật thuộc tính. Một cách rõ ràng hơn là tạo giá trị mới rồi gọi session.setAttribute("items", updatedItems), đồng thời chọn save mode phù hợp.

## 7. Repository khác nhau, ranh giới API vẫn giống nhau

Spring Session cung cấp các repository implementation để lưu phiên ở những hệ thống khác nhau. Mã ứng dụng làm việc với abstraction SessionRepository, còn implementation đảm nhận việc ánh xạ dữ liệu phiên vào kho cụ thể.

| Repository / kho lưu | Cách lưu tổng quát | Điều cần lưu ý |
| --- | --- | --- |
| Map hoặc repository trong bộ nhớ | Giữ phiên trong cấu trúc dữ liệu của tiến trình | Phù hợp cho kiểm thử hoặc tình huống đơn giản; không tự chia sẻ dữ liệu giữa nhiều tiến trình |
| Redis | Lưu dữ liệu phiên trong cấu trúc dữ liệu Redis và áp dụng thời hạn tương ứng | Các instance cần cùng Redis, namespace và cấu hình tương thích |
| JDBC | Lưu dữ liệu phiên trong các bảng cơ sở dữ liệu quan hệ | Các instance cần cùng database/schema; cần quan tâm tải truy vấn và dọn dữ liệu hết hạn |

API tạo và lưu có thể giống nhau, nhưng đặc tính vận hành không giống nhau. Repository trong bộ nhớ thường mất trạng thái khi tiến trình dừng và mỗi instance có vùng lưu riêng. Redis có thể cung cấp truy cập nhanh và TTL ở kho dữ liệu, nhưng phụ thuộc kết nối và cấu hình khả dụng của Redis. JDBC tận dụng hệ quản trị cơ sở dữ liệu quan hệ, nhưng lưu lượng session làm tăng tải database.

Một kho dữ liệu dùng chung chỉ phát huy tác dụng khi các instance thực sự kết nối đến cùng đích lưu trữ và dùng cấu hình tương thích. Nếu Instance A lưu vào Redis namespace app-a còn Instance B tìm trong namespace app-b, B không thể tìm thấy phiên dù cả hai dùng cùng máy chủ Redis.

### TTL và hết hạn

Phiên thường có khoảng thời gian không hoạt động tối đa. Repository có thể dùng giá trị này để xác định thời điểm phiên hết hạn và, tùy implementation, cấu hình TTL ở kho dữ liệu hoặc cơ chế dọn dữ liệu. Cần phân biệt:

- **Giá trị hết hạn của phiên:** quy tắc cho biết một phiên còn hợp lệ hay không.
- **TTL của bản ghi trong kho:** thời gian dữ liệu được giữ trước khi kho tự loại bỏ hoặc đánh dấu hết hạn.
- **Dọn dữ liệu vật lý:** tác vụ loại bỏ bản ghi đã hết hạn khỏi bảng hoặc cấu trúc lưu trữ.

Các cơ chế này không nhất thiết xảy ra cùng một thời điểm. Với JDBC, bản ghi hết hạn có thể còn tồn tại vật lý cho đến khi tác vụ dọn dữ liệu chạy; điều đó không đồng nghĩa ứng dụng được phép coi phiên đã hết hạn là hợp lệ. Với Redis, TTL có thể làm key tự hết hạn, nhưng ứng dụng vẫn cần xử lý trường hợp không tìm thấy phiên.

## 8. Lỗi thường gặp khi nhầm tạo phiên với lưu phiên

### Tạo phiên nhưng không lưu

Mã gọi createSession, đặt thuộc tính và trả ID về client mà bỏ qua save. Client gửi ID trong request sau nhưng repository không có phiên để tải. Cách sửa là lưu thành công trước khi công bố ID hoặc dùng SessionRepositoryFilter để quản lý vòng đời qua HttpSession.

### Lưu trước rồi tiếp tục thay đổi nhưng không lưu lại

Ứng dụng gọi save, sau đó thay đổi thêm thuộc tính trên cùng đối tượng nhưng không gọi save lần nữa. Những lần đọc sau có thể chỉ nhìn thấy trạng thái đã lưu ở lần trước. Cần lưu sau mỗi nhóm thay đổi cần được giữ lại.

### Cho rằng object được chia sẻ giữa các instance

Hai instance cùng dùng một repository không có nghĩa chúng cùng giữ một tham chiếu Java. Instance B phải tải trạng thái qua repository. Nếu A thay đổi object trong bộ nhớ nhưng chưa lưu, B không thể thấy thay đổi đó.

### Cho rằng save bảo đảm mọi cập nhật đồng thời

Hai request có thể cùng tải một phiên, cùng sửa một thuộc tính rồi lưu theo thứ tự khác nhau. Kết quả cuối cùng có thể phụ thuộc thứ tự ghi và cách repository xử lý cập nhật. save là thao tác lưu trạng thái phiên; nó không tự biến một chuỗi đọc-sửa-ghi thành thao tác nguyên tử. Với dữ liệu cần tính đúng đắn khi cập nhật đồng thời, dùng giao dịch, lệnh nguyên tử của kho dữ liệu hoặc thiết kế dữ liệu phù hợp.

### Dùng repository trong bộ nhớ để kết luận hệ thống nhiều instance hoạt động

Một bài kiểm thử với repository trong bộ nhớ chỉ xác nhận logic API trong một tiến trình. Nó không xác nhận hai instance có thể chia sẻ session. Kiểm thử tích hợp cần dùng cùng loại kho chia sẻ mà hệ thống dự kiến vận hành, hoặc một cấu hình tương đương.

### Bỏ qua lỗi lưu

Khi Redis hoặc database không khả dụng, save có thể thất bại. Nếu ứng dụng vẫn gửi session ID như thể phiên đã được lưu, request sau có thể không tìm thấy trạng thái. Cần xử lý lỗi lưu theo chính sách của ứng dụng, ghi log có kiểm soát và phát cảnh báo. Không ghi session ID hoặc dữ liệu nhạy cảm của phiên vào log.

## 9. Kiểm thử sự khác nhau giữa tạo và lưu

Một bài kiểm thử repository nên kiểm tra riêng từng giai đoạn:

1. Gọi createSession() và đặt một thuộc tính.
2. Xác nhận mã ứng dụng chưa gọi save ở giai đoạn này.
3. Gọi save(session).
4. Dùng findById(session.getId()) để tải phiên.
5. Kiểm tra thuộc tính đã được lưu.
6. Thay đổi thuộc tính, gọi save lần nữa và tải lại để xác nhận giá trị mới.
7. Gọi deleteById rồi xác nhận lần tìm sau không còn trả về phiên.

Đối với repository trong bộ nhớ, bài kiểm thử này có thể xác nhận hợp đồng API và cách mã ứng dụng sử dụng save. Để xác nhận tính chia sẻ, cần chạy hai ứng dụng hoặc hai tiến trình kết nối cùng kho dữ liệu:

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant R as SessionRepository / kho dùng chung
    participant B as Instance B
    A->>R: createSession()
    R-->>A: Session mới trong bộ nhớ A
    A->>A: setAttribute(userId)
    A->>R: save(session)
    R-->>A: Lưu thành công
    B->>R: findById(sessionId)
    R-->>B: Dữ liệu phiên đã lưu
    B->>B: Đọc userId trên object riêng
~~~

Một kiểm thử khác nên cố ý bỏ qua save để chứng minh đối tượng mới không tự trở thành dữ liệu dùng chung. Khi kiểm thử repository thật, hãy dọn dữ liệu sau mỗi test, dùng namespace hoặc database riêng cho test và không để các test dùng chung session ID có thể ảnh hưởng lẫn nhau.

## 10. Nguyên tắc thiết kế khi sử dụng API

- Dùng HttpSession và SessionRepositoryFilter cho phần lớn luồng web Servlet; để filter quản lý việc tạo, nạp, lưu, xóa và cookie.
- Dùng SessionRepository trực tiếp khi thật sự cần thao tác ở mức repository, chẳng hạn một thành phần hạ tầng hoặc tác vụ quản trị phiên. Khi đó phải quản lý tường minh việc lưu sau khi tạo và sau khi cập nhật.
- Chỉ công bố session ID sau khi phiên đã được lưu thành công và có cơ chế xác thực, bảo vệ cookie hoặc token phù hợp.
- Lưu lượng và dữ liệu phiên nên nhỏ, có cấu trúc ổn định, tương thích với cơ chế tuần tự hóa của repository. Điều này giúp tránh lỗi khi nhiều phiên bản ứng dụng cùng chạy trong rolling deployment.
- Đặt TTL phù hợp với yêu cầu bảo mật và nghiệp vụ; không giữ phiên vô hạn để né việc xử lý hết hạn.
- Xem save là ranh giới ghi dữ liệu, không phải cơ chế đồng bộ tham chiếu Java hoặc khóa giao dịch cho mọi thao tác đồng thời.
- Kiểm thử cả trường hợp tạo nhưng không lưu, cập nhật nhưng quên lưu, hết hạn, xóa phiên và lỗi kết nối kho.

Khi nắm rõ ranh giới này, việc sử dụng Spring Session trở nên dễ dự đoán hơn: đối tượng phiên biểu diễn trạng thái trong lần xử lý hiện tại, repository quản lý vòng đời lưu trữ, còn Redis hoặc JDBC giữ dữ liệu để các instance khác có thể tải lại. Tạo phiên là bước khởi đầu của vòng đời; lưu phiên mới làm cho trạng thái đó có thể được truy xuất qua kho dữ liệu.
