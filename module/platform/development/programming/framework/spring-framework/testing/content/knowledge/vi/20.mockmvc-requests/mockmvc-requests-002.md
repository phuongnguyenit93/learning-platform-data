# Query parameter, form parameter và encoding

Khi kiểm thử một endpoint Spring MVC bằng MockMvc, ta thường phải gửi dữ liệu qua URL hoặc qua phần body của request. Hai cách phổ biến là **query parameter** và **form parameter**. Cả hai đều có thể được Spring bind vào tham số của controller bằng **@RequestParam**, nhưng chúng nằm ở hai vị trí khác nhau trong HTTP request và có quy tắc encoding cần hiểu rõ.

Ví dụ, hai request sau có thể mang cùng một cặp dữ liệu:

~~~http
GET /search?keyword=spring&page=2
~~~

~~~http
POST /search
Content-Type: application/x-www-form-urlencoded

keyword=spring&page=2
~~~

Request thứ nhất truyền dữ liệu trong query string của URI. Request thứ hai truyền dữ liệu trong body theo định dạng form URL-encoded. Khi dùng Servlet API, cả query string và form body đều có thể góp phần tạo nên request parameter map. Vì thế, controller dùng @RequestParam có thể nhận giá trị từ cả hai nguồn.

## 1. Query parameter nằm trong URI

Query parameter xuất hiện sau dấu hỏi chấm trong URI. Các cặp tên và giá trị thường được ngăn cách bằng dấu ampersand:

~~~text
/products?keyword=java&page=2&tag=spring&tag=mvc
~~~

Trong ví dụ này:

- keyword có giá trị java.
- page có giá trị 2.
- tag xuất hiện hai lần, lần lượt là spring và mvc.

Query parameter phù hợp với dữ liệu dùng để xác định hoặc lọc tài nguyên, chẳng hạn từ khóa tìm kiếm, bộ lọc, thứ tự sắp xếp và số trang. Với GET request, đây thường là cách truyền dữ liệu đầu vào chính.

Một controller có thể nhận các giá trị này bằng @RequestParam:

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/products")
    ProductSearchResult search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(name = "tag", required = false) List<String> tags
    ) {
        List<String> selectedTags = tags == null ? List.of() : tags;
        return new ProductSearchResult(keyword, page, selectedTags);
    }
}

record ProductSearchResult(
    String keyword,
    int page,
    List<String> tags
) {}
~~~

MockMvc có thể tạo query string bằng queryParam:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/products")
        .queryParam("keyword", "spring")
        .queryParam("page", "2")
        .queryParam("tag", "spring", "mvc"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.keyword").value("spring"))
    .andExpect(jsonPath("$.page").value(2))
    .andExpect(jsonPath("$.tags[0]").value("spring"))
    .andExpect(jsonPath("$.tags[1]").value("mvc"));
~~~

queryParam thể hiện rõ dữ liệu thuộc query string. Có thể truyền nhiều giá trị cho cùng một tên để kiểm tra tham số lặp. Khi cần xác nhận cả URL hoặc query string thực tế, hãy dùng API này thay vì chỉ thêm dữ liệu vào parameter map.

## 2. Form parameter nằm trong request body

Form parameter thường được gửi bằng POST với media type application/x-www-form-urlencoded. Body chứa các cặp tên và giá trị theo dạng:

~~~text
username=alice&city=Hanoi
~~~

Định dạng này có cấu trúc gần giống query string, nhưng dữ liệu nằm trong body. Trình duyệt thường tạo kiểu request này khi gửi một HTML form thông thường không dùng multipart upload.

Một endpoint xử lý form có thể dùng @RequestParam:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @PostMapping(
        path = "/profile",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    ProfileResult update(
        @RequestParam String displayName,
        @RequestParam String city
    ) {
        return new ProfileResult(displayName, city);
    }
}

record ProfileResult(String displayName, String city) {}
~~~

Trong MockMvc, cách phổ biến để kiểm tra binding của form field là dùng param cùng content type phù hợp:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("displayName", "Nguyễn Văn An")
        .param("city", "Hồ Chí Minh"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Nguyễn Văn An"))
    .andExpect(jsonPath("$.city").value("Hồ Chí Minh"));
~~~

Ở đây, param đưa các giá trị đã được giải mã vào parameter map của request mô phỏng. Cách này rất phù hợp để kiểm tra controller binding, validation và kết quả xử lý. Nó không tự kiểm tra việc một chuỗi byte URL-encoded trong body được Servlet container giải mã như thế nào. Nếu mục tiêu là kiểm tra chính bước parse body ở tầng HTTP, cần kiểm thử qua server/container thực tế hoặc cấu hình request builder và filter phù hợp với phiên bản Spring đang dùng.

Nếu muốn bind toàn bộ form vào một object, có thể dùng @ModelAttribute:

~~~java
public class RegistrationForm {
    private String displayName;
    private String city;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

~~~java
@PostMapping(
    path = "/registration",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
RegistrationForm register(@ModelAttribute RegistrationForm form) {
    return form;
}
~~~

Test có thể gửi từng field:

~~~java
mockMvc.perform(post("/registration")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("displayName", "Lan")
        .param("city", "Da Nang"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Lan"))
    .andExpect(jsonPath("$.city").value("Da Nang"));
~~~

## 3. Phân biệt queryParam, param và form data trong MockMvc

MockMvc có một số API trông khá giống nhau nhưng phục vụ các mục đích khác nhau:

| API | Ý nghĩa khi dựng request | Khi nên dùng |
|---|---|---|
| queryParam(name, values...) | Thêm giá trị vào query string của URI và request parameter map. | Khi muốn mô tả rõ query parameter và kiểm tra cách URL được tạo. |
| param(name, values...) | Thêm giá trị trực tiếp vào request parameter map. | Khi kiểm tra binding của @RequestParam mà không cần mô phỏng vị trí truyền dữ liệu trên wire. |
| params(multiValueMap) | Thêm một nhóm request parameter đã chuẩn bị. | Khi test có nhiều tham số hoặc dữ liệu được tạo từ fixture. |
| content(body) | Đặt raw request body. | Khi endpoint đọc body, hoặc khi cần kiểm thử payload ở mức nội dung. |
| contentType(mediaType) | Đặt Content-Type của request. | Khi endpoint yêu cầu form, JSON hoặc một media type cụ thể. |

Một điểm rất quan trọng: param không đồng nghĩa với việc tạo query string. Nó đặt giá trị vào parameter map của MockHttpServletRequest. Vì vậy, test dùng param có thể làm controller nhận được @RequestParam nhưng không chứng minh rằng URL có đúng query string mong muốn.

Ngược lại, queryParam biểu đạt rõ dữ liệu nằm trong URI. Với form URL-encoded, param thường là lựa chọn thuận tiện để kiểm tra quá trình bind form field vào controller. Hãy đặt contentType thành application/x-www-form-urlencoded để request mô phỏng thể hiện đúng loại nội dung endpoint yêu cầu.

Không nên dùng content("a=1&b=2") rồi mặc định rằng MockMvc sẽ parse body thành Servlet parameters giống hệt một HTTP server thật trong mọi cấu hình. Raw body và parameter map là hai phần riêng biệt của request mô phỏng. Chọn API theo đúng tầng hành vi muốn kiểm tra.

## 4. @RequestParam nhận dữ liệu từ đâu?

Trong Spring MVC chạy trên Servlet API, @RequestParam liên kết với request parameters. Parameter map của Servlet request có thể chứa dữ liệu được phân tích từ query string và từ form body của request phù hợp.

Điều này có nghĩa một controller như sau:

~~~java
@GetMapping("/search")
SearchResult search(@RequestParam String keyword) {
    return new SearchResult(keyword);
}
~~~

có thể nhận keyword từ:

~~~http
GET /search?keyword=spring
~~~

Và một controller nhận form:

~~~java
@PostMapping(
    path = "/search",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
SearchResult searchForm(@RequestParam String keyword) {
    return new SearchResult(keyword);
}
~~~

có thể nhận keyword từ form body:

~~~http
POST /search
Content-Type: application/x-www-form-urlencoded

keyword=spring
~~~

Nếu cùng một tên xuất hiện ở cả query string và form body, Servlet request có thể cung cấp nhiều giá trị cho cùng parameter name. Không nên xây dựng logic dựa trên giả định rằng một nguồn luôn thắng nguồn còn lại. Nếu API cần phân biệt hai vị trí, hãy thiết kế hợp đồng đầu vào rõ ràng và kiểm thử riêng từng nguồn.

### Các trường hợp binding cần kiểm thử

| Trường hợp | Hành vi cần xác nhận |
|---|---|
| Tham số bắt buộc bị thiếu | Mặc định Spring trả lỗi client, thường là HTTP 400 do thiếu request parameter. |
| Tham số có defaultValue | Giá trị mặc định được dùng khi tham số thiếu hoặc rỗng theo quy tắc của @RequestParam. |
| required = false | Controller có thể nhận null khi tham số không được gửi. |
| Optional<T> | Có thể biểu diễn tham số không bắt buộc bằng Optional. |
| Nhiều giá trị cùng tên | Dùng List<T> hoặc mảng để nhận nhiều giá trị. |
| Sai kiểu dữ liệu | Kiểm tra lỗi chuyển đổi, ví dụ chuỗi không thể chuyển thành int. |
| Giá trị rỗng | Phân biệt parameter bị thiếu với parameter có giá trị chuỗi rỗng nếu nghiệp vụ cần phân biệt. |

Ví dụ kiểm tra tham số lặp:

~~~java
mockMvc.perform(get("/products")
        .queryParam("tag", "spring", "mvc", "testing"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tags.length()").value(3));
~~~

Ví dụ kiểm tra tham số bắt buộc:

~~~java
mockMvc.perform(get("/products"))
    .andExpect(status().isBadRequest());
~~~

Ví dụ kiểm tra default value:

~~~java
mockMvc.perform(get("/products")
        .queryParam("keyword", "spring"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page").value(1));
~~~

## 5. URL encoding và form encoding

HTTP request truyền dữ liệu qua URI hoặc body dưới dạng chuỗi byte. Các ký tự ngoài tập ký tự an toàn phải được biểu diễn theo quy tắc encoding phù hợp. Với URI, cách biểu diễn phổ biến là percent-encoding: mỗi byte được viết thành dấu phần trăm theo sau bởi hai chữ số hexadecimal.

Với form URL-encoded, tên và giá trị được nối bằng dấu bằng, các cặp được nối bằng dấu ampersand. Dấu cách thường được biểu diễn bằng dấu cộng. Những ký tự có ý nghĩa cấu trúc như ampersand, dấu bằng, dấu cộng hoặc dấu phần trăm trong chính giá trị cần được encode để không bị hiểu nhầm là cú pháp phân tách.

Ví dụ, giá trị:

~~~text
red & blue + green
~~~

không thể được chèn nguyên xi vào một form body vì dấu ampersand có thể bị hiểu là bắt đầu một field mới. Dạng form-encoded tương ứng có thể là:

~~~text
color=red+%26+blue+%2B+green
~~~

Trong đó:

- Dấu cách được biểu diễn bằng dấu cộng trong form encoding.
- Ký tự ampersand bên trong giá trị được biểu diễn bằng %26.
- Dấu cộng thực sự trong giá trị được biểu diễn bằng %2B.

Với tiếng Việt, các ký tự được mã hóa thành byte UTF-8 rồi percent-encode. Ví dụ, một phần giá trị Nguyễn Văn An có thể xuất hiện trong form body dưới dạng:

~~~text
Nguy%E1%BB%85n+V%C4%83n+An
~~~

Điều quan trọng là phải phân biệt **giá trị Java đã giải mã** với **chuỗi được truyền trên wire**. Khi dùng MockMvc param hoặc queryParam, ta truyền giá trị logic như Nguyễn Văn An. Không nên tự encode trước rồi lại đưa chuỗi đã encode vào các API này, vì kết quả có thể bị double-encoding hoặc controller nhận nguyên các ký tự %.

### Dấu cộng và dấu cách

Trong form URL-encoded, dấu cộng đại diện cho dấu cách. Vì vậy, nếu giá trị thực sự chứa dấu cộng, phải encode thành %2B. Ví dụ:

~~~text
q=C%2B%2B
~~~

biểu diễn giá trị C++.

Nếu gửi:

~~~text
q=C++
~~~

thì bộ giải mã form có thể hiểu thành C cùng hai dấu cách. Đây là lỗi phổ biến khi tự nối query string hoặc form body bằng tay.

### Dấu ampersand và dấu bằng

Dấu ampersand phân tách các cặp parameter, còn dấu bằng phân tách tên với giá trị. Nếu chúng xuất hiện bên trong dữ liệu, cần encode:

| Ký tự trong giá trị | Biểu diễn percent-encoded |
|---|---|
| & | %26 |
| = | %3D |
| + | %2B |
| % | %25 |

Không nên encode toàn bộ chuỗi query cùng lúc. Hãy encode từng tên và từng giá trị theo đúng API xây dựng URI hoặc form body, để các dấu phân tách cấu trúc vẫn được giữ nguyên.

## 6. Encoding trong test MockMvc

MockMvc có thể kiểm tra các giá trị đã giải mã bằng cách truyền trực tiếp String vào queryParam hoặc param:

~~~java
mockMvc.perform(get("/search")
        .queryParam("keyword", "cà phê & trà")
        .queryParam("sort", "name+asc"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.keyword").value("cà phê & trà"))
    .andExpect(jsonPath("$.sort").value("name+asc"));
~~~

Khi dựng URI, MockMvc xử lý việc đưa giá trị query vào request. Ta không cần tự thay dấu cách bằng dấu cộng hay thay dấu ampersand bằng %26 trước khi gọi queryParam.

Với form parameter, cách kiểm thử binding thông thường cũng truyền giá trị đã giải mã:

~~~java
mockMvc.perform(post("/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding("UTF-8")
        .param("displayName", "Nguyễn Văn An")
        .param("note", "A&B + C"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Nguyễn Văn An"))
    .andExpect(jsonPath("$.note").value("A&B + C"));
~~~

characterEncoding đặt encoding của request mô phỏng. Tuy nhiên, khi dùng param, các giá trị đã được cung cấp trực tiếp dưới dạng Java String. Test này xác nhận binding nhận đúng ký tự Unicode; nó không xác nhận byte của form body đã được encode và decode chính xác.

Nếu cần tạo chuỗi form-encoded thủ công, Java có URLEncoder với charset UTF-8:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String encodedName = URLEncoder.encode(
    "Nguyễn Văn An",
    StandardCharsets.UTF_8
);
~~~

URLEncoder tạo dữ liệu theo quy tắc application/x-www-form-urlencoded, trong đó dấu cách trở thành dấu cộng. Nó phù hợp khi chủ động tạo form body. Không nên dùng URLEncoder để encode một giá trị rồi truyền vào queryParam hoặc param, vì các API MockMvc này nhận giá trị logic chưa encode.

Nếu cần kiểm tra chính việc giải mã raw form body, hãy xác định rõ Servlet container, request encoding và filter đang xử lý request. Một bài test MockMvc dùng parameter map có thể kiểm tra controller binding rất tốt, nhưng không thay thế hoàn toàn kiểm thử HTTP end-to-end cho bộ giải mã form của container.

## 7. Charset của request và dữ liệu Unicode

Encoding không chỉ là việc thay ký tự bằng %xx. Hai phía cần thống nhất charset để chuyển đổi giữa byte và ký tự. Nếu client gửi UTF-8 nhưng server giải mã bằng charset khác, dữ liệu có thể bị lỗi mojibake, ví dụ ký tự tiếng Việt biến thành chuỗi ký tự lạ.

Khi mô phỏng form request trong MockMvc, có thể chỉ rõ:

~~~java
mockMvc.perform(post("/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .param("displayName", "Đặng Thị Mai"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").value("Đặng Thị Mai"));
~~~

Với request thật, cấu hình encoding phải được áp dụng trước khi Servlet container đọc request parameters. Trong ứng dụng Spring MVC, cần kiểm tra cấu hình encoding của web stack và các filter liên quan, đặc biệt khi hỗ trợ client cũ hoặc dữ liệu form có Unicode. Không nên cho rằng chỉ đặt charset trong một chỗ bất kỳ là đủ cho mọi tầng.

Query string và form body có đường xử lý khác nhau. Query string được phân tích từ URI; form body được phân tích theo content type và request encoding. Vì vậy, nếu lỗi chỉ xuất hiện ở một nguồn, hãy kiểm tra riêng đường truyền và cách giải mã của nguồn đó.

## 8. Khi nào dùng query parameter, form parameter hay request body?

| Kiểu dữ liệu | Vị trí truyền | Ví dụ | Cách test thường dùng |
|---|---|---|---|
| Query parameter | URI sau dấu ? | GET /products?category=book | get(...).queryParam(...) |
| Form parameter | Body application/x-www-form-urlencoded | POST /login với username và password | post(...).contentType(APPLICATION_FORM_URLENCODED).param(...) |
| JSON request body | Body application/json | POST /orders với object JSON | post(...).contentType(APPLICATION_JSON).content(...) |
| Multipart field/file | Body multipart/form-data | Upload ảnh kèm mô tả | multipart(...) với param/file part phù hợp |
| Path variable | Một đoạn của URI path | GET /orders/123 | get("/orders/{id}", 123) |

Query parameter thường phù hợp với điều kiện lọc và truy vấn. Form parameter phù hợp với dữ liệu nhập từ HTML form. JSON body thường phù hợp với API nhận một object có cấu trúc. Path variable biểu diễn định danh hoặc phân cấp tài nguyên. Multipart dùng cho upload file hoặc form có nhiều loại part.

Đừng dùng @RequestBody để nhận dữ liệu form theo thói quen khi endpoint được thiết kế để bind Servlet request parameters. Với form URL-encoded trong Spring MVC, @RequestParam và @ModelAttribute thường phù hợp hơn. Với JSON, dùng @RequestBody và gửi đúng application/json.

## 9. Một bộ test thực tế cho query và form

Một test class dùng @WebMvcTest có thể khởi tạo controller và MockMvc để kiểm tra request binding mà không cần chạy HTTP server thật:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest({ProfileController.class, ProductController.class})
class ProfileControllerTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void bindsQueryParameters() throws Exception {
        mockMvc.perform(get("/products")
                .queryParam("keyword", "cà phê & trà")
                .queryParam("page", "2")
                .queryParam("tag", "spring", "mvc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.keyword").value("cà phê & trà"))
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.tags[0]").value("spring"))
            .andExpect(jsonPath("$.tags[1]").value("mvc"));
    }

    @Test
    void bindsUrlEncodedFormParameters() throws Exception {
        mockMvc.perform(post("/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .param("displayName", "Nguyễn Văn An")
                .param("city", "Hồ Chí Minh"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Nguyễn Văn An"))
            .andExpect(jsonPath("$.city").value("Hồ Chí Minh"));
    }
}
~~~

Ví dụ minh họa hai request độc lập. Trong dự án thực tế, thay controller và endpoint bằng lớp đang được kiểm thử; nếu controller phụ thuộc service, cấu hình mock bean theo phiên bản Spring Boot của dự án. Không cần khởi động server thật khi mục tiêu chỉ là xác nhận mapping và binding của Spring MVC.

Nên bổ sung các ca kiểm thử theo hợp đồng API:

1. Query parameter bình thường với một giá trị ASCII.
2. Query parameter có dấu cách, tiếng Việt, dấu cộng và dấu ampersand.
3. Nhiều giá trị cho cùng một tên parameter.
4. Form field Unicode và giá trị có ký tự đặc biệt.
5. Thiếu parameter bắt buộc, parameter rỗng và default value.
6. Giá trị không chuyển đổi được sang kiểu dữ liệu đích.
7. Request sai Content-Type khi endpoint có khai báo consumes.

## 10. Các lỗi thường gặp

### Dùng param rồi kết luận query string đã đúng

param thêm dữ liệu vào request parameter map. Nếu cần kiểm tra URI query string, hãy dùng queryParam hoặc kiểm tra request URI/query string bằng cách phù hợp. Hai mục tiêu này không giống nhau.

### Encode giá trị hai lần

Nếu gọi URLEncoder trước rồi truyền kết quả vào queryParam hoặc param, dấu phần trăm trong chuỗi đã encode có thể tiếp tục bị encode. Ví dụ, %26 có thể thành %2526. Hãy truyền giá trị gốc vào MockMvc builder.

### Nhầm dấu cộng với dấu cách

Trong form encoding, dấu cộng biểu diễn dấu cách. Dấu cộng thật trong dữ liệu phải được biểu diễn bằng %2B trên wire. Khi dùng param hoặc queryParam, truyền dấu cộng thật trong Java String và để builder xử lý.

### Bỏ qua Content-Type của form

Một request POST có param không tự động chứng minh endpoint đã nhận đúng loại form. Nếu endpoint yêu cầu application/x-www-form-urlencoded, hãy đặt contentType tương ứng và kiểm tra cả trường hợp sai media type khi cần.

### Nghĩ rằng content(body) tự tạo request parameters

content đặt raw body. param đặt request parameters. Hai API này có vai trò khác nhau. Nếu controller bind bằng @RequestParam, hãy chắc chắn test đã cung cấp parameter theo cách mà MockHttpServletRequest hỗ trợ.

### Chỉ test ASCII

Các giá trị đơn giản như abc không bộc lộ lỗi encoding. Nên có test với tiếng Việt, dấu cách, dấu cộng, dấu ampersand và ký tự phần trăm để phát hiện sai khác giữa dữ liệu logic và dữ liệu truyền trên wire.

### Nhầm form URL-encoded với JSON

application/x-www-form-urlencoded và application/json là hai định dạng khác nhau. Một endpoint nhận @RequestParam hoặc @ModelAttribute không tương đương endpoint nhận @RequestBody. Test phải gửi đúng Content-Type và cấu trúc dữ liệu mà controller công bố.

## 11. Cách chọn API MockMvc

Khi viết một test request, hãy bắt đầu từ hợp đồng HTTP của endpoint:

1. Nếu dữ liệu nằm trong URI sau dấu hỏi chấm, dùng queryParam để biểu đạt query string.
2. Nếu muốn kiểm tra binding của Servlet request parameters mà không quan tâm vị trí truyền dữ liệu, dùng param.
3. Nếu gửi form URL-encoded, đặt Content-Type thành application/x-www-form-urlencoded và dùng param cho bài test binding thông thường.
4. Nếu cần kiểm tra raw body hoặc quá trình parse/encoding ở tầng HTTP, dùng kiểm thử phù hợp với raw body và Servlet container; không suy luận điều đó chỉ từ parameter map.
5. Nếu endpoint nhận JSON, gửi JSON body với application/json và kiểm tra @RequestBody.
6. Nếu giá trị có Unicode hoặc ký tự cấu trúc, truyền dữ liệu gốc vào builder và kiểm tra giá trị controller nhận được.

Hiểu rõ vị trí của dữ liệu, vai trò của từng MockMvc request builder và ranh giới giữa giá trị đã giải mã với byte được truyền trên wire sẽ giúp test phản ánh đúng hợp đồng HTTP. Query parameter, form parameter và encoding có liên quan chặt chẽ, nhưng mỗi phần cần được kiểm tra ở đúng tầng của request.
