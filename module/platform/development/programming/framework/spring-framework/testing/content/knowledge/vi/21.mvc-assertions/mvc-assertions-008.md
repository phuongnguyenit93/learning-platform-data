# Redirect, forward và flash attributes

Trong Spring MVC, một controller có thể trả về view name để yêu cầu framework điều hướng request đến một tài nguyên khác. Hai cơ chế thường gặp là **redirect** và **forward**. Redirect yêu cầu client thực hiện một HTTP request mới đến URL đích; forward chuyển tiếp request hiện tại ở phía server. Khi cần mang một thông báo hoặc dữ liệu tạm thời qua redirect, Spring cung cấp **flash attributes**.

Spring MVC Test cho phép kiểm tra các kết quả này bằng `MockMvc`. Ta có thể xác nhận status và URL redirect, URL được forward, các thuộc tính flash được tạo ra, cũng như dữ liệu flash xuất hiện trong request tiếp theo. Các matcher quan trọng gồm `redirectedUrl(...)`, `redirectedUrlPattern(...)`, `forwardedUrl(...)`, `forwardedUrlPattern(...)`, `flash()` và `model()`.

## 1. Controller trả về view name

Redirect và forward theo cú pháp view name thường được dùng với controller khai báo `@Controller`:

```java
@Controller
class OrderController {

    @PostMapping("/orders")
    String createOrder() {
        return "redirect:/orders/42";
    }
}
```

Spring xử lý chuỗi trả về như tên view. Prefix `redirect:` yêu cầu framework tạo redirect view; prefix `forward:` yêu cầu tạo forward view.

Không nhầm cách trả về view name này với `@RestController`. `@RestController` bao gồm `@ResponseBody`, vì vậy chuỗi `"redirect:/orders/42"` sẽ được ghi như response body thay vì được diễn giải thành redirect view. Nếu endpoint trả dữ liệu REST, hãy dùng cơ chế HTTP response phù hợp như `ResponseEntity` và header `Location`; nếu muốn trả view name, dùng `@Controller` hoặc phương thức được đánh dấu `@ResponseBody` một cách có chủ đích.

## 2. Redirect: client gửi một request mới

Redirect là kết quả điều hướng ở tầng HTTP. Controller trả về view name bắt đầu bằng `redirect:`:

```java
@Controller
@RequestMapping("/orders")
class OrderController {

    @PostMapping
    String create(@RequestParam String customer) {
        // Tạo đơn hàng và lấy id của đơn hàng mới.
        return "redirect:/orders/42";
    }
}
```

Spring tạo response redirect, thường có status 302 theo cấu hình mặc định của `RedirectView`, và header `Location` chỉ đến URL đích. Client nhận response này rồi thực hiện request mới đến địa chỉ đó. Trong luồng Post/Redirect/Get (PRG), client gửi POST để tạo dữ liệu, nhận redirect và sau đó GET trang kết quả. Cách này giúp thao tác refresh trang kết quả không lặp lại POST ban đầu.

Với `MockMvc`, có thể kiểm tra redirect như sau:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42"));
```

`status().is3xxRedirection()` xác nhận response thuộc nhóm redirect. `redirectedUrl(...)` kiểm tra URL đích được đặt trong response. Nếu hợp đồng yêu cầu chính xác status 302, có thể dùng `status().isFound()`; nếu ứng dụng chủ động trả 303 See Other, hãy kiểm tra `status().isSeeOther()`. Nên dùng matcher chính xác khi status là một phần của hợp đồng HTTP.

### Redirect với path variable và query parameter

`RedirectAttributes.addAttribute(...)` đưa dữ liệu vào URL redirect. Giá trị có thể được dùng để mở rộng URI template hoặc được thêm thành query parameter.

```java
@PostMapping
String create(
        @RequestParam String customer,
        RedirectAttributes redirectAttributes
) {
    long orderId = 42L;
    redirectAttributes.addAttribute("id", orderId);
    redirectAttributes.addAttribute("source", "checkout");
    return "redirect:/orders/{id}";
}
```

Trong ví dụ, `id` được dùng để thay thế `{id}` trong đường dẫn; `source` trở thành query parameter. Test có thể kiểm tra URL kết quả:

```java
mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42?source=checkout"));
```

Nếu giá trị động làm URL khó so sánh tuyệt đối, có thể dùng `redirectedUrlPattern(...)` để kiểm tra theo pattern. `redirectedUrl(...)` và `redirectedUrlPattern(...)` giúp xác nhận đích điều hướng, còn matcher status xác nhận loại response.

## 3. Forward: chuyển tiếp request ở phía server

Forward là thao tác nội bộ của server thông qua `RequestDispatcher`. Client không nhận response redirect để gửi request mới. URL trên trình duyệt vẫn là URL ban đầu; request hiện tại được chuyển đến tài nguyên hoặc servlet đích trong cùng ứng dụng.

Controller có thể trả về view name bắt đầu bằng `forward:`:

```java
@Controller
class ReportController {

    @GetMapping("/reports/{id}/preview")
    String preview(@PathVariable long id, Model model) {
        model.addAttribute("reportId", id);
        return "forward:/internal/reports/preview";
    }
}
```

Prefix `forward:` yêu cầu Spring sử dụng cơ chế forward đến đường dẫn đã chỉ định. Vì đây là dispatch nội bộ, không có response 3xx và không có header `Location` yêu cầu client điều hướng.

Test có thể xác nhận URL forward:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/reports/42/preview"))
        .andExpect(status().isOk())
        .andExpect(forwardedUrl("/internal/reports/preview"));
```

`forwardedUrl(...)` kiểm tra đích dispatch nội bộ được ghi nhận bởi request giả lập. `forwardedUrlPattern(...)` có thể dùng khi muốn so sánh theo pattern.

Forward giữ nguyên request hiện tại. Vì không có request mới từ client, phương thức HTTP và các thuộc tính request tiếp tục thuộc cùng luồng xử lý. Điều này khác redirect, nơi client xử lý response 3xx rồi tạo request mới theo semantics của status code và hành vi client.

### Forward đến tài nguyên view

Forward cũng có thể được dùng để chuyển đến tài nguyên nội bộ, chẳng hạn JSP nằm dưới `WEB-INF`:

```java
@GetMapping("/reports/{id}")
String view(@PathVariable long id, Model model) {
    model.addAttribute("reportId", id);
    return "forward:/WEB-INF/views/reports/detail.jsp";
}
```

Trong ứng dụng thực tế, servlet container và view technology xử lý tài nguyên đích. `MockMvc` có thể xác nhận URL forward và model trong kết quả MVC; nó không render JSP như một servlet container đầy đủ. Nếu cần xác nhận việc render template hoặc JSP thực tế, cần test tích hợp phù hợp với view technology đang dùng.

## 4. So sánh redirect và forward

| Đặc điểm | Redirect | Forward |
| --- | --- | --- |
| Nơi thực hiện | Client nhận response redirect rồi gửi request mới. | Server chuyển tiếp request hiện tại. |
| HTTP response ban đầu | Status thuộc nhóm 3xx và thường có `Location`. | Không tạo response 3xx chỉ vì forward. |
| URL phía client | Được cập nhật sang URL đích sau khi client theo redirect. | Vẫn là URL ban đầu. |
| Request | Một request mới được tạo sau redirect. | Tiếp tục request hiện tại. |
| Dữ liệu truyền tiếp | Có thể dùng URL attributes hoặc flash attributes. | Có thể dùng request attributes và model trong cùng request. |
| Matcher chính | `redirectedUrl(...)`, `redirectedUrlPattern(...)`. | `forwardedUrl(...)`, `forwardedUrlPattern(...)`. |

Chọn redirect khi muốn kết thúc request hiện tại và điều hướng client, đặc biệt trong PRG sau thao tác POST. Chọn forward khi server cần chuyển tiếp nội bộ request đến một tài nguyên hoặc servlet khác mà không yêu cầu client gửi request mới.

## 5. Flash attributes dùng để làm gì?

Khi redirect, model thông thường không tự động tồn tại trong request tiếp theo vì redirect tạo một request mới. Nếu cần hiển thị thông báo như “Đã tạo đơn hàng thành công” ở trang đích, có thể dùng flash attribute.

Flash attribute là dữ liệu tạm thời được lưu trong `FlashMap` để chuyển từ request hiện tại sang request tiếp theo. Spring sử dụng `FlashMapManager` để lưu và khôi phục flash map; sau khi được request phù hợp nhận, dữ liệu flash được dùng một lần rồi loại bỏ. Flash attribute không được thêm vào query string của URL.

Trong controller, tiêm `RedirectAttributes` và gọi `addFlashAttribute(...)`:

```java
@PostMapping
String create(
        @RequestParam String customer,
        RedirectAttributes redirectAttributes
) {
    long orderId = 42L;

    redirectAttributes.addAttribute("id", orderId);
    redirectAttributes.addFlashAttribute("notice", "Order created successfully");

    return "redirect:/orders/{id}";
}
```

Ở đây:

- `addAttribute("id", orderId)` tạo dữ liệu phục vụ URL redirect.
- `addFlashAttribute("notice", ...)` lưu thông báo vào output flash map để request đích nhận được.
- `return "redirect:/orders/{id}"` tạo response redirect đến trang chi tiết.

Flash attribute phù hợp với thông báo tạm thời, kết quả thao tác hoặc dữ liệu nhỏ cần hiển thị ngay sau redirect. Không nên dùng flash map để chuyển các payload lớn hoặc dữ liệu cần lưu trữ lâu dài.

## 6. Kiểm tra flash attributes trên response redirect

Spring MVC Test cung cấp `flash()` result matcher để kiểm tra output flash map được tạo trong request hiện tại.

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;

mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42"))
        .andExpect(flash().attribute(
                "notice", "Order created successfully"));
```

Một số matcher hữu ích:

| Matcher | Điều được xác nhận |
| --- | --- |
| `flash().attribute(name, value)` | Flash map có thuộc tính với tên và giá trị mong đợi. |
| `flash().attributeExists(name)` | Thuộc tính flash có tồn tại. |
| `flash().attributeDoesNotExist(name)` | Thuộc tính flash không tồn tại. |
| `flash().attributeCount(count)` | Số lượng thuộc tính trong flash map. |

Có thể kết hợp matcher để xác nhận cả số lượng và nội dung:

```java
mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(flash().attributeCount(1))
        .andExpect(flash().attributeExists("notice"))
        .andExpect(flash().attributeDoesNotExist("debugInfo"));
```

`flash()` kiểm tra dữ liệu flash được tạo bởi request đang xét. Nó khác `model()`, vốn kiểm tra model của request xử lý hiện tại. Flash map là cơ chế mang dữ liệu qua ranh giới redirect; model là dữ liệu được dùng trong quá trình render hoặc xử lý request hiện tại.

## 7. Kiểm tra request đích nhận flash attributes

Sau khi xác nhận redirect response tạo đúng flash map, có thể mô phỏng request tiếp theo và đưa các flash attributes đó vào request builder bằng `.flashAttrs(...)`.

Controller đích có thể nhận flash attribute thông qua `Model`:

```java
@GetMapping("/{id}")
String detail(@PathVariable long id, Model model) {
    model.addAttribute("orderId", id);
    return "orders/detail";
}
```

Test thực hiện request POST, lấy flash map từ kết quả, rồi gửi GET đến URL đích:

```java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult redirectResult = mockMvc.perform(post("/orders")
                .param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

mockMvc.perform(get("/orders/42")
                .flashAttrs(redirectResult.getFlashMap()))
        .andExpect(status().isOk())
        .andExpect(model().attribute("notice", "Order created successfully"))
        .andExpect(model().attribute("orderId", 42L));
```

`MvcResult.getFlashMap()` trả về output flash map được tạo bởi request đầu tiên. `flashAttrs(...)` đặt các giá trị đó thành input flash attributes của request GET giả lập. Khi Spring MVC xử lý request đích, các giá trị flash được đưa vào model, vì vậy `model().attribute(...)` có thể kiểm tra thông báo mà view sẽ nhận.

Cách mô phỏng này tập trung kiểm tra hai phần: request tạo flash data và controller đích sử dụng dữ liệu đó. Nó chủ động chuyển map từ kết quả trước sang request sau. Nếu mục tiêu là kiểm tra toàn bộ vòng đời lưu/khôi phục flash map qua session và `FlashMapManager`, cần thiết kế test tích hợp với cùng session và cơ chế quản lý flash map thực tế.

## 8. Phân biệt URL attributes, flash attributes và model attributes

Ba loại dữ liệu này có vòng đời và vị trí sử dụng khác nhau:

| Loại thuộc tính | Cách tạo | Nơi xuất hiện | Vòng đời |
| --- | --- | --- | --- |
| Redirect URL attribute | `RedirectAttributes.addAttribute(...)` | Path variable hoặc query string của URL redirect. | Có trong URL và request được gửi đến đích. |
| Flash attribute | `RedirectAttributes.addFlashAttribute(...)` | Input flash map của request tiếp theo, sau đó có thể xuất hiện trong model. | Tạm thời, thường được tiêu thụ một lần. |
| Model attribute | `Model.addAttribute(...)` hoặc `ModelMap.addAttribute(...)` | Model của request hiện tại để view sử dụng. | Gắn với request/render hiện tại. |

Ví dụ:

```java
redirectAttributes.addAttribute("id", 42L);
redirectAttributes.addFlashAttribute("notice", "Created");
```

`id` có thể xuất hiện trong đường dẫn `/orders/42`; `notice` được lưu trong flash map. Nếu thay bằng `model.addAttribute("notice", "Created")` rồi trả về `redirect:/orders/42`, model thông thường không tự chuyển sang request GET mới.

Không đưa mật khẩu, token hoặc dữ liệu nhạy cảm vào URL attributes vì URL có thể xuất hiện trong lịch sử trình duyệt, log và referrer. Flash attributes tránh việc đưa giá trị vào query string, nhưng vẫn chỉ nên chứa dữ liệu tạm thời phù hợp với cơ chế session của ứng dụng.

## 9. Kiểm tra redirect và forward với pattern

Khi URL đích có phần động, có thể dùng pattern matcher thay vì so sánh toàn bộ URL.

Ví dụ redirect đến một đường dẫn chứa mã được tạo trong lúc chạy:

```java
mockMvc.perform(post("/reports").param("title", "Annual report"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrlPattern("/reports/*"));
```

Tương tự với forward:

```java
mockMvc.perform(get("/reports/42/export"))
        .andExpect(forwardedUrlPattern("/internal/reports/*"));
```

Pattern matcher hữu ích khi một phần URL phụ thuộc dữ liệu động nhưng cấu trúc đường dẫn vẫn là điều cần xác nhận. Nếu URL chính xác là một phần của hợp đồng, ưu tiên matcher URL tuyệt đối để test phát hiện thay đổi ngoài ý muốn.

## 10. Kiểm tra `RedirectView` và status code

Ngoài cú pháp chuỗi `redirect:`, controller có thể trả về một `RedirectView` để cấu hình redirect rõ ràng hơn:

```java
@PostMapping("/orders")
RedirectView create() {
    RedirectView view = new RedirectView("/orders/42");
    view.setStatusCode(HttpStatus.SEE_OTHER);
    return view;
}
```

`HttpStatus.SEE_OTHER` tương ứng 303. Status này thường được dùng trong PRG để client truy cập trang đích bằng GET sau một POST. Nếu dùng RedirectView với status tùy chỉnh, test nên kiểm tra đúng status và URL:

```java
mockMvc.perform(post("/orders"))
        .andExpect(status().isSeeOther())
        .andExpect(redirectedUrl("/orders/42"));
```

Redirect có thể dùng các status khác tùy semantics HTTP và nhu cầu của client. 302 và 303 thường dẫn đến hành vi truy cập lại bằng GET trong các trình duyệt phổ biến; 307 và 308 được định nghĩa để giữ nguyên method và body khi redirect. Hãy chọn status có chủ đích và kiểm tra đúng điều mà client cần tuân theo.

## 11. Lỗi thường gặp khi kiểm thử redirect, forward và flash

**Dùng `@RestController` rồi mong chuỗi `redirect:` được xử lý.**

`@RestController` ghi chuỗi trả về vào response body. Dùng `@Controller` cho view name, hoặc trả `ResponseEntity` với status và `Location` nếu endpoint là REST API.

**Chỉ kiểm tra status 3xx mà không kiểm tra URL.**

Một response redirect có thể trỏ nhầm đích mà status vẫn đúng. Kết hợp `status().is3xxRedirection()` với `redirectedUrl(...)` hoặc `redirectedUrlPattern(...)`.

**Dùng `forwardedUrl` để kiểm tra redirect.**

Redirect và forward là hai cơ chế khác nhau. Dùng `redirectedUrl(...)` cho response redirect và `forwardedUrl(...)` cho dispatch nội bộ.

**Mong model thông thường tồn tại sau redirect.**

Redirect tạo request mới. Dùng `addFlashAttribute(...)` cho dữ liệu tạm thời cần chuyển sang request tiếp theo, hoặc `addAttribute(...)` nếu dữ liệu phù hợp để đưa vào URL.

**Kiểm tra flash attribute bằng `model()` trên request POST.**

Flash attributes được ghi vào output flash map của request redirect. Dùng `flash()` để kiểm tra map đó. Chỉ kiểm tra bằng `model()` trên request đích sau khi cung cấp input flash attributes.

**Quên truyền flash map khi mô phỏng request tiếp theo.**

Trong test mô phỏng thủ công, dùng `.flashAttrs(redirectResult.getFlashMap())` trên request đích. Nếu muốn kiểm tra việc lưu/khôi phục tự động qua session, cần test với cơ chế `FlashMapManager` và cùng session.

**Cho rằng forward sẽ tạo request mới từ client.**

Forward là dispatch nội bộ, không có response redirect cho trình duyệt. Nếu cần thay đổi URL trên client hoặc thực hiện PRG, hãy dùng redirect.

**Cho rằng matcher forward xác nhận tài nguyên JSP đã render.**

`forwardedUrl(...)` xác nhận đích forward trong kết quả MockMvc. Nó không chứng minh servlet container đã render JSP hoặc template engine đã tạo HTML cuối cùng.

## 12. Quy trình kiểm thử kết quả điều hướng

Khi viết test cho controller có điều hướng, xác định trước cơ chế mà controller cần thực hiện:

1. Nếu client cần truy cập URL mới, kiểm tra redirect status và `Location` bằng `redirectedUrl(...)` hoặc `redirectedUrlPattern(...)`.
2. Nếu server cần chuyển tiếp request hiện tại, kiểm tra đích bằng `forwardedUrl(...)` hoặc `forwardedUrlPattern(...)`.
3. Nếu redirect cần mang dữ liệu tạm thời, dùng `addFlashAttribute(...)` và kiểm tra output map bằng `flash()`.
4. Nếu cần xác nhận trang đích nhận dữ liệu flash, lấy `MvcResult.getFlashMap()` rồi truyền qua `.flashAttrs(...)` vào request tiếp theo.
5. Nếu dữ liệu cần xuất hiện trong URL, dùng `addAttribute(...)` và kiểm tra chính xác đường dẫn hoặc query string.
6. Nếu status redirect có ý nghĩa cụ thể như 302 hay 303, kiểm tra đúng status thay vì chỉ kiểm tra chung nhóm 3xx.
7. Nếu cần xác nhận view được render bởi servlet container hoặc template engine, bổ sung test tích hợp phù hợp.

## Kết luận

Redirect tạo response 3xx để client gửi request mới; forward chuyển tiếp request hiện tại ở phía server. Spring MVC Test cung cấp `redirectedUrl(...)` và `forwardedUrl(...)` để kiểm tra hai kết quả này. Flash attributes dùng `FlashMap` để chuyển dữ liệu tạm thời qua redirect và có thể được kiểm tra bằng `flash()` hoặc đưa vào request tiếp theo trong test bằng `.flashAttrs(...)`.

Phân biệt đúng URL attributes, flash attributes và model attributes giúp test xác nhận dữ liệu xuất hiện đúng nơi và đúng thời điểm. Khi kiểm tra chỉ riêng controller, MockMvc có thể xác nhận URL điều hướng và model/flash map; việc render view hoặc vòng đời servlet đầy đủ cần được kiểm tra ở mức tích hợp phù hợp.
