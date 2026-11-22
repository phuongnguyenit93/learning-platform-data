# Filter, FilterChain và nguyên tắc gọi `chain.doFilter` trong Servlet

## 1. Vì sao phải hiểu FilterChain trước khi học Spring Security?

Trong ứng dụng web dùng Servlet, yêu cầu HTTP không nhất thiết đến `HttpServlet` hoặc Spring MVC controller ngay lập tức. Servlet container (ví dụ Tomcat) có thể cho request đi qua nhiều `Filter` để xử lý các mối quan tâm chung như ghi log, mã hóa ký tự, CORS, kiểm soát truy cập hoặc chuyển tiếp đến cơ chế bảo mật. Các filter đó phối hợp thông qua `FilterChain`.

Câu lệnh trung tâm là **`chain.doFilter(request, response)`**: filter hiện tại nhường quyền xử lý cho phần còn lại của chuỗi. Khi lời gọi này kết thúc, luồng thực thi quay về ngay sau dòng `chain.doFilter` của filter hiện tại, nên một filter có thể thực hiện công việc **trước** và **sau** phần xử lý phía dưới.

Hiểu đúng ba khái niệm là điều kiện tiên quyết để đọc luồng Spring Security Servlet:

- **`Filter`**: thành phần chặn tại tầng Servlet; phương thức `doFilter` nhận request, response và một `FilterChain`.
- **`FilterChain`**: đối tượng do môi trường chạy cung cấp để gọi filter kế tiếp, hoặc đích cuối của chuỗi (servlet / cơ chế dispatch đích).
- **`chain.doFilter(...)`**: thao tác tiếp tục chuỗi; nó không tự động có nghĩa là “cho phép truy cập”, cũng không tạo một HTTP request mới.

Giản đồ cho một request có hai filter đã được đăng ký theo thứ tự A rồi B:

```text
HTTP request
    |
    v
Filter A: xử lý trước
    |
    | A gọi chain.doFilter
    v
Filter B: xử lý trước
    |
    | B gọi chain.doFilter
    v
Servlet / Spring MVC DispatcherServlet
    |
    | xử lý hoàn tất, trả quyền điều khiển
    v
Filter B: xử lý sau
    |
    v
Filter A: xử lý sau
    |
    v
HTTP response
```

Vì thế, các bước “trước” chạy theo thứ tự **A → B → đích**, còn các bước “sau” chạy theo thứ tự **đích → B → A**. Thứ tự thực tế do đăng ký filter và loại dispatch quyết định; tên lớp hoặc thứ tự khai báo trong ví dụ không tự bảo đảm thứ tự ngoài thực tế.

## 2. Hợp đồng Servlet API và vòng đời

Trên Spring Boot 3 / Spring Framework 6 và Jakarta Servlet hiện đại, kiểu và phương thức cơ bản nằm trong `jakarta.servlet`:

```java
public interface Filter {
    void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
    ) throws IOException, ServletException;
}

public interface FilterChain {
    void doFilter(
        ServletRequest request,
        ServletResponse response
    ) throws IOException, ServletException;
}
```

Đây là **trích giản lược chữ ký liên quan**, không phải toàn bộ mã nguồn của các interface. `Filter` còn có các hook vòng đời `init(FilterConfig)` và `destroy()`; ứng dụng thông thường chỉ cần ghi đè `doFilter` nếu không cần khởi tạo/giải phóng riêng.

- **Khởi tạo**: container tạo/khởi tạo filter theo cấu hình; `init` có thể nhận cấu hình của filter.
- **Phục vụ request**: container gọi `doFilter` cho những request hoặc dispatch khớp mapping. Một instance filter có thể phục vụ đồng thời nhiều request trên các thread khác nhau.
- **Hủy**: container gọi `destroy` khi ngừng sử dụng filter theo vòng đời của nó.

**Hệ quả về thread safety:** đừng đặt trạng thái của từng request vào field có thể thay đổi của một filter dùng chung, chẳng hạn `private String currentUser` hoặc `private long startTime`. Hãy dùng biến cục bộ trong `doFilter`, thuộc tính của request khi thích hợp, hoặc cơ chế quản lý ngữ cảnh có dọn dẹp đúng cách.

`ServletRequest` và `ServletResponse` là kiểu tổng quát. Với một ứng dụng HTTP, chúng thường là `HttpServletRequest` và `HttpServletResponse`; chỉ ép kiểu khi chắc chắn filter đang xử lý HTTP. Filter có thể truyền nguyên các đối tượng xuống dưới hoặc bọc chúng bằng `ServletRequestWrapper` / `ServletResponseWrapper` để điều chỉnh cách đọc/ghi. Trong mọi trường hợp, tham số truyền vào `chain.doFilter` quyết định đối tượng mà tầng tiếp theo nhận được.

## 3. Điều gì xảy ra tại `chain.doFilter`?

Xét cấu trúc điển hình:

```java
// Minh họa phần thân phương thức doFilter
before(request);
try {
    chain.doFilter(request, response);
} finally {
    after(request);
}
```

`before` và `after` ở đây chỉ là tên thao tác mô tả trình tự, **không phải chương trình Java độc lập**. Khi chạy:

1. Filter hiện tại thực hiện bước trước chuỗi.
2. `chain.doFilter` chuyển quyền cho phần còn lại của chuỗi. Filter kế tiếp có thể tiếp tục, trả lỗi, bọc request/response hoặc dừng xử lý.
3. Khi phía dưới trả về bình thường hoặc ném ngoại lệ, khối `finally` của filter hiện tại vẫn chạy.
4. Nếu phía dưới ném ngoại lệ, sau khi `finally` hoàn tất, ngoại lệ tiếp tục lan truyền trừ khi có tầng khác xử lý nó.

Lệnh `chain.doFilter` **không bắt buộc phải chạy trong mọi nhánh**. Một filter có quyền chặn request (short-circuit) nếu nó đã xử lý response hợp lệ. Ví dụ: filter chặn endpoint bảo trì có thể trả HTTP 503 và `return` mà không tới servlet. Tuy nhiên, một filter dùng để quan sát hoặc ghi log thông thường cần chuyển tiếp để ứng dụng hoạt động.

Một nguyên tắc thực hành hữu ích:

> Với **một lần thực thi `doFilter`** theo nhánh chuyển tiếp thông thường, gọi `chain.doFilter(request, response)` **đúng một lần**. Chỉ không gọi khi chủ ý kết thúc request hoặc xử lý chuyển hướng/response khác. Đừng gọi nhiều lần trừ khi có thiết kế đặc biệt và kiểm chứng hệ quả.

Đây là nguyên tắc thiết kế cho phần lớn filter, không phải ràng buộc cú pháp của Java API: interface không ngăn bạn gọi 0 hoặc 2 lần, nhưng các lựa chọn đó thay đổi nghiêm trọng luồng xử lý.

## 4. Ví dụ Servlet Filter thật: đo thời gian xử lý

Ví dụ sau dành cho môi trường web chạy **Jakarta Servlet API**. Lớp không có `main`; nó được Servlet container gọi khi request khớp mapping.

```java
package example.web;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.annotation.WebFilter;
import jakarta.servlet.http.HttpServletRequest;

import java.io.IOException;

@WebFilter(
    urlPatterns = "/*",
    dispatcherTypes = DispatcherType.REQUEST
)
public final class RequestTimingFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        long startedAt = System.nanoTime();

        System.out.println("ENTER " + httpRequest.getRequestURI());
        try {
            // Truyền tiếp request và response gốc.
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;
            System.out.println(
                    "EXIT  " + httpRequest.getRequestURI()
                    + " after " + elapsedMs + " ms"
            );
        }
    }
}
```

**Giải thích:**

- `@WebFilter` mô tả URL mapping. Mẫu `/*` áp dụng trên các URL trong ứng dụng cho loại dispatch `REQUEST`; nó **không tự bảo đảm** filter được kích hoạt trong mọi cách chạy Spring Boot.
- Trong Spring Boot dùng embedded servlet container, cần cơ chế đăng ký tương ứng, chẳng hạn `@ServletComponentScan` để quét `@WebFilter`, **hoặc** dùng `FilterRegistrationBean`. Chọn một cơ chế đăng ký cho cùng filter để tránh chạy trùng.
- `try/finally` giúp ghi dòng `EXIT` cả khi đoạn phía dưới ném ngoại lệ; nó không nuốt ngoại lệ và cũng không gọi lại chain.
- Giá trị thời gian đo phụ thuộc thực tế; không có stdout cố định để cam kết. Nếu request khởi tạo xử lý bất đồng bộ, thời gian trên chỉ bao quanh **lời gọi đồng bộ** hiện tại, không tự bao gồm toàn bộ công việc async.
- Trong ứng dụng thật, thường thay `System.out` bằng logger phù hợp và cân nhắc không ghi dữ liệu nhạy cảm.

Nếu biên dịch lớp riêng ngoài Spring Boot, cần cung cấp `jakarta.servlet-api` trên compile classpath (chẳng hạn Jakarta Servlet 6.0 cho một môi trường phù hợp) và triển khai vào Servlet container; **`java example.web.RequestTimingFilter` không phải lệnh chạy hợp lệ** vì lớp không có `main`.

## 5. Chạy độc lập bằng Java 17: quan sát thứ tự chính xác

Để tự thấy luồng chạy mà không cần Tomcat, chương trình dưới đây **mô phỏng nguyên tắc tiếp tục chuỗi** bằng interface riêng. `Step` / `Next` **không phải** `jakarta.servlet.Filter` / `FilterChain`; đây là mô hình học tập có thể chạy với Java 17 trở lên.

Tạo file `FilterChainDemo.java`:

```java
import java.util.List;

public class FilterChainDemo {
    record Request(String path) {}

    @FunctionalInterface
    interface Next {
        void run(Request request);
    }

    @FunctionalInterface
    interface Step {
        void run(Request request, Next chain);
    }

    static Next compose(List<Step> filters, Next endpoint) {
        Next next = endpoint;

        for (int i = filters.size() - 1; i >= 0; i--) {
            Step current = filters.get(i);
            Next remainder = next;
            next = request -> current.run(request, remainder);
        }
        return next;
    }

    public static void main(String[] args) {
        Step audit = (request, chain) -> {
            System.out.println("audit: before");
            try {
                chain.run(request);
            } finally {
                System.out.println("audit: after");
            }
        };

        Step guard = (request, chain) -> {
            if (request.path().equals("/blocked")) {
                System.out.println("guard: blocked");
                return;
            }
            System.out.println("guard: pass");
            chain.run(request);
        };

        Next endpoint = request ->
                System.out.println("endpoint: " + request.path());

        Next pipeline = compose(List.of(audit, guard), endpoint);

        System.out.println("=== /ok ===");
        pipeline.run(new Request("/ok"));
        System.out.println("=== /blocked ===");
        pipeline.run(new Request("/blocked"));
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac FilterChainDemo.java
java FilterChainDemo
```

Stdout chính xác:

```text
=== /ok ===
audit: before
guard: pass
endpoint: /ok
audit: after
=== /blocked ===
audit: before
guard: blocked
audit: after
```

Ở `/ok`, `audit` gọi phần còn lại, `guard` tiếp tục và endpoint chạy. Ở `/blocked`, `guard` trả về ngay: endpoint **không** chạy, nhưng `audit` vẫn tiếp tục ở khối `finally`. Đó là cách đọc stack lời gọi của `chain.doFilter` trong servlet thật.

## 6. Khi nào được phép không gọi chain?

Một filter có thể tự kết thúc request khi chủ ý tạo response, ví dụ chặn đường dẫn đang bảo trì. Trong một `doFilter` dành cho HTTP, đoạn sau minh họa một quyết định cụ thể:

```java
HttpServletRequest req = (HttpServletRequest) request;
HttpServletResponse res = (HttpServletResponse) response;

if (req.getRequestURI().equals(req.getContextPath() + "/maintenance")) {
    res.sendError(
            HttpServletResponse.SC_SERVICE_UNAVAILABLE,
            "Endpoint temporarily unavailable"
    );
    return; // Chủ ý dừng, không gọi chain.doFilter.
}

chain.doFilter(request, response);
```

Đây là **đoạn code bên trong phương thức `doFilter`**, cần import `jakarta.servlet.http.HttpServletRequest` / `HttpServletResponse` và ngữ cảnh filter phù hợp để sử dụng; không phải lớp độc lập.

Ba điều phải phân biệt:

- **Chuyển tiếp:** gọi chain đúng một lần để filter/servlet phía sau xử lý.
- **Chặn có chủ đích:** đặt trạng thái, body hoặc redirect hợp lệ cho response rồi kết thúc nhánh. Có thể dùng `sendError`, `sendRedirect` hoặc ghi response tùy bài toán; không gọi chain sau khi đã quyết định chặn.
- **Lỗi ngoài ý muốn:** ngoại lệ được ném/lan truyền; chỉ `return` trong im lặng sẽ dễ tạo tình huống controller không chạy mà phía client nhận response trống hoặc trạng thái mặc định gây hiểu nhầm.

Không dùng ví dụ chặn theo header tùy ý để thay thế xác thực và phân quyền của Spring Security. Ở đây mục đích chỉ là phân biệt **tiếp tục chuỗi** và **kết thúc chuỗi**.

## 7. Bẫy hay gặp với `chain.doFilter`

| Mẫu sai hoặc giả định sai | Hệ quả / cách sửa |
| --- | --- |
| Quên gọi `chain.doFilter` trong filter ghi log | Controller/servlet không được gọi, dù filter có thể không báo lỗi. Xác định nhánh chặn chủ ý, còn nhánh bình thường phải tiếp tục. |
| Gọi `chain.doFilter` hai lần trong cùng nhánh | Đoạn phía dưới có thể bị thực thi lặp, ghi response hai lần hoặc ném lỗi. Đừng dùng chain như một “hàm retry”. |
| Đặt lời gọi chain vào `finally` sau khi đã chạy nó ở `try` | Khi kết thúc hay gặp ngoại lệ sẽ gọi tiếp lần nữa. Chỉ đặt phần **dọn dẹp** cần thiết trong `finally`. |
| `sendError` / `sendRedirect` rồi vẫn gọi chain | Tầng sau có thể thử ghi thêm vào response đã quyết định xử lý hoặc đã commit. `return` ở nhánh đã kết thúc. |
| Nuốt `IOException` / `ServletException` rồi coi request thành công | Che mất lỗi thực tế. Chỉ bắt khi xử lý có chủ đích, nếu không để ngoại lệ lan truyền. |
| Ghi header/body sau `chain.doFilter` mà mặc định response chưa gửi | Servlet phía dưới có thể đã commit response; sau đó không còn bảo đảm thay đổi header/status có tác dụng. Điều chỉnh ở thời điểm phù hợp hoặc dùng wrapper nếu thực sự cần. |
| Đọc hết request body trong filter rồi truyền xuống không bọc request | Servlet/controller phía sau có thể không còn body để đọc. Cần chiến lược buffering/wrapper đúng API nếu muốn đọc lại. |
| Lưu dữ liệu của request vào field của filter | Các request đồng thời có thể đè dữ liệu nhau. Dùng local variable hoặc request-scoped state. |
| Thấy filter chạy nhiều lần rồi kết luận `chain.doFilter` đã bị gọi hai lần | Có thể do nhiều dispatcher, filter bị đăng ký trùng, nhiều request thật, hoặc cơ chế async/error. Kiểm tra registration, dispatcher và request ID trước. |

**Vì sao `finally` vẫn quan trọng?** Nó phù hợp cho giải phóng tài nguyên hoặc xóa ngữ cảnh do filter tự thiết lập. Nếu sử dụng `ThreadLocal` / MDC, cần dọn dẹp ở `finally` để tránh dữ liệu request cũ rò sang công việc khác trên cùng thread. Tuy nhiên, ở xử lý bất đồng bộ, thread của các giai đoạn có thể khác nhau: không nên coi một `ThreadLocal` là ngữ cảnh bền vững của toàn bộ request.

## 8. Mapping, thứ tự và các loại dispatcher

Filter không được kích hoạt chỉ vì có một lớp implements `Filter`. Servlet container cần **đăng ký** filter và **ánh xạ** nó tới URL/servlet và loại dispatch. Những nguồn đăng ký thường gặp là `web.xml`, `@WebFilter` được container quét, hoặc cấu hình chương trình như `FilterRegistrationBean` trong Spring Boot.

Các loại dispatch của Servlet bao gồm:

- `REQUEST`: request đi vào qua đường HTTP thông thường.
- `FORWARD`: chuyển tiếp nội bộ qua `RequestDispatcher.forward`.
- `INCLUDE`: bao gồm tài nguyên qua `RequestDispatcher.include`.
- `ASYNC`: dispatch trong luồng xử lý bất đồng bộ.
- `ERROR`: dispatch để xử lý lỗi theo cơ chế của container.

Filter được gọi ở dispatch nào phụ thuộc **dispatcherTypes** được ánh xạ. Vì vậy câu “mỗi request chỉ chạy filter một lần” không phải chân lý chung: một HTTP request có thể trải qua nhiều dispatch, và mỗi dispatch có thể khớp filter khác nhau. Tương tự, gọi `chain.doFilter` một lần **trong mỗi invocation** không có nghĩa filter sẽ chỉ được container gọi một lần trong toàn bộ vòng đời HTTP request.

Thứ tự giữa filter cũng phải được cấu hình và kiểm chứng. Với Spring Boot, `FilterRegistrationBean#setOrder` là một cách điều chỉnh thứ tự của filter **cấp servlet container**. Thứ tự giữa các filter **bên trong Spring Security** do cấu hình/security infrastructure quyết định; không suy ra nó trực tiếp từ thứ tự đăng ký ở container.

**Ghi nhớ về async và error:** `chain.doFilter` có thể trả về sau khi endpoint đã bắt đầu xử lý async, trong khi response chưa hoàn tất. Đo thời gian toàn bộ request hoặc dọn ngữ cảnh qua nhiều dispatch đòi hỏi hiểu `AsyncContext` / `AsyncListener`, dispatcher mapping và cơ chế async của framework. Khi lỗi dẫn tới error dispatch, filter có thể xuất hiện ở một lần gọi khác nếu mapping cho phép.

## 9. Liên hệ cụ thể với Spring Security Servlet

Spring Security sử dụng chính hợp đồng filter của Servlet nhưng bổ sung tầng điều phối nội bộ. Một sơ đồ khái niệm thường gặp:

```text
Servlet container FilterChain
  |
  v
DelegatingFilterProxy ("springSecurityFilterChain")
  |
  v
Spring bean FilterChainProxy
  |
  +--> chọn SecurityFilterChain đầu tiên khớp request
          |
          +--> các Security Filter theo thứ tự được cấu hình
                    |
                    +--> gọi tiếp phần còn lại của Servlet FilterChain
                              |
                              v
                         DispatcherServlet / endpoint
```

Các tên nghe giống nhau nhưng có trách nhiệm khác nhau:

- **`jakarta.servlet.FilterChain`** là hợp đồng tiếp tục chuỗi tại tầng Servlet.
- **`DelegatingFilterProxy`** là một Servlet Filter ủy quyền tới bean của Spring; tên bean thường dùng là `springSecurityFilterChain`.
- **`FilterChainProxy`** điều phối các filter bảo mật, chọn chuỗi bảo mật phù hợp với request và chạy các filter trong chuỗi đó.
- **`SecurityFilterChain`** trong Spring Security đại diện cho **danh sách filter bảo mật và điều kiện khớp request**. Nó không phải biến `chain` được truyền trực tiếp trong `Filter#doFilter`.

Khi một security filter gọi `chain.doFilter`, nó tiếp tục bước tiếp theo **trong chuỗi mà nó đang tham gia**. Việc xác thực, từ chối truy cập, redirect đăng nhập hoặc xử lý ngoại lệ có thể khiến luồng **không đi tới controller**. Điều đó không nhất thiết là lỗi; phải quan sát quyết định của từng filter và response thực tế.

**Hai cảnh báo tích hợp thực tế:**

1. Một filter tự viết có thể đăng ký trực tiếp ở **Servlet container** hoặc được đưa vào **Spring Security filter chain**, tùy mục đích. Nếu đồng thời tự động được Boot đăng ký như Servlet Filter bean và được thêm vào chuỗi Security, nó có thể chạy trùng. Hãy kiểm tra cơ chế đăng ký; nếu chỉ dùng trong Security chain, có thể cần tắt servlet registration riêng của bean đó.
2. Spring cung cấp `OncePerRequestFilter` để hỗ trợ logic “một lần” theo cách framework quản lý, nhưng vẫn phải hiểu xử lý `ASYNC` / `ERROR` và các hook liên quan như `shouldNotFilterAsyncDispatch`, `shouldNotFilterErrorDispatch`. Tên lớp không thay thế việc hiểu dispatcher và đăng ký filter.

Trong bài nền tảng Servlet này, điểm cần nắm là cơ chế **gọi xuống – trả ngược lên – có thể dừng có chủ đích**. Cấu hình xác thực, phân quyền và thứ tự security filter chi tiết thuộc phần chuyên sâu tương ứng.

## 10. Cách đọc và debug một chuỗi filter thực tế

Khi endpoint không được gọi hoặc filter xuất hiện hai lần, bắt đầu từ một request có thể tái hiện và lần lượt xác minh:

1. **Registration:** filter được đăng ký ở container, trong Spring Security, hay cả hai? Kiểm tra URL pattern và dispatcher types thay vì chỉ nhìn annotation.
2. **Entry:** đặt breakpoint/log đầu `doFilter`; ghi method, URI, dispatcher type và request ID phù hợp; tránh ghi bí mật như token hoặc session ID.
3. **Continue:** xác định nhánh nào gọi `chain.doFilter`, nhánh nào `return`, `sendError` hoặc `sendRedirect`; đặt breakpoint ngay trước/sau lời gọi.
4. **Order:** với hai filter, so sánh log `before/after`; nếu thấy A.before → B.before → B.after → A.after thì đó là cấu trúc lồng nhau bình thường.
5. **Outcome:** phân biệt ngoại lệ được ném, response được commit, dispatch `ERROR` và xử lý async; một dòng `after` không chứng minh client đã nhận đủ response.
6. **Security:** nếu dùng Spring Security, kiểm tra chuỗi `SecurityFilterChain` nào khớp request và có filter nào trả response trước controller.

Ví dụ suy luận không cần chạy server:

- A gọi chain; B gọi chain; servlet trả về → `A.before, B.before, servlet, B.after, A.after`.
- A gọi chain; B gửi 403 rồi return → servlet không chạy; phần sau `chain.doFilter` của A vẫn chạy.
- B ném `ServletException` → khối `finally` của A vẫn chạy; ngoại lệ tiếp tục đi lên nếu không bị xử lý.
- A gọi chain hai lần → **không thể** mặc định coi là hai lần lọc “vô hại”; có thể làm endpoint hoặc phần chuỗi còn lại chạy lại.

## 11. Tự kiểm tra kiến thức

**Tình huống 1.** Filter A chỉ ghi log trước và sau; Filter B chặn `/admin` và ghi response 403. Với request `/admin`, controller có chạy không? Filter A có ghi log sau không?

**Đáp án:** Controller không chạy vì B không gọi chain. Nếu A dùng `try/finally` bao quanh lời gọi chain, A vẫn ghi log sau khi B trả quyền điều khiển.

**Tình huống 2.** Đưa một filter tự viết thành Spring bean, đồng thời thêm nó vào `SecurityFilterChain`. Log xuất hiện hai lần. Có chắc `chain.doFilter` đã bị gọi hai lần trong code không?

**Đáp án:** Chưa chắc. Cần kiểm tra filter có đang được servlet container tự đăng ký **và** được chạy trong Spring Security hay không; ngoài ra xem dispatcher type và số request thật.

**Tình huống 3.** Tại sao không được khẳng định “`finally` của filter chạy xong nghĩa là response HTTP đã hoàn tất”?

**Đáp án:** `finally` chỉ cho biết lời gọi đồng bộ phía dưới đã trả về hoặc ném lỗi. Xử lý async có thể tiếp tục, container có thể còn thực hiện error dispatch hoặc hoàn tất response sau đó.

## 12. Ghi nhớ để áp dụng

- `Filter` bao quanh quá trình xử lý ở tầng Servlet; `FilterChain` đại diện cho phần công việc còn lại.
- `chain.doFilter(request, response)` chính là điểm **chuyển tiếp**; khi trả về, filter hiện tại có thể xử lý hậu kỳ.
- Với nhánh đi tiếp thông thường, gọi chain **một lần**; khi chủ ý chặn, tạo response hợp lệ rồi dừng; không vô tình bỏ qua hoặc gọi lặp.
- Dùng `try/finally` cho dọn dẹp, lưu ý ngoại lệ, response commit và async; không đặt lời gọi chain lần hai trong `finally`.
- Kiểm tra registration, thứ tự, dispatcher type và tính an toàn đồng thời trước khi kết luận filter “chạy sai”.
- Spring Security xây trên cùng nguyên tắc Servlet FilterChain nhưng thêm `DelegatingFilterProxy`, `FilterChainProxy` và `SecurityFilterChain` để điều phối các filter bảo mật.
