# So sánh JSON có hoặc không yêu cầu thứ tự nghiêm ngặt

## Mục tiêu của phép so sánh JSON trong kiểm thử MVC

Khi kiểm thử một endpoint Spring MVC bằng MockMvc, kết quả HTTP thường chứa JSON trong response body. Ta cần xác nhận nội dung phản hồi đúng với hợp đồng của API: các trường quan trọng có mặt, giá trị chính xác, cấu trúc object và array phù hợp, đồng thời thứ tự phần tử được kiểm tra khi thứ tự là một phần của hợp đồng.

Không nên so sánh JSON bằng cách so sánh hai chuỗi nguyên văn. Hai JSON có thể biểu diễn cùng một dữ liệu nhưng khác khoảng trắng, xuống dòng hoặc thứ tự khai báo các thuộc tính trong object. Ví dụ, hai object sau có ý nghĩa tương đương:

~~~json
{"id": 42, "status": "PAID"}
~~~

~~~json
{
  "status": "PAID",
  "id": 42
}
~~~

Theo ngữ nghĩa JSON, object là tập hợp các cặp tên và giá trị; thứ tự thuộc tính không mang ý nghĩa. Ngược lại, array là một dãy có thứ tự. Hai array chứa cùng phần tử nhưng sắp xếp khác nhau có thể biểu diễn hai kết quả khác nhau nếu API cam kết thứ tự.

Spring MVC Test cung cấp matcher **content().json(...)** để phân tích và so sánh JSON theo cấu trúc. Phép so sánh này giúp test tập trung vào dữ liệu trả về thay vì định dạng chuỗi do Jackson hoặc serializer tạo ra.

## So sánh nghiêm ngặt và không nghiêm ngặt bằng MockMvc

Trong Spring Framework 6.1 (nền tảng thường gặp ở Spring Boot 3.3), ContentResultMatchers có hai cách gọi quan trọng:

- **content().json(expectedJson, true):** so sánh nghiêm ngặt.
- **content().json(expectedJson, false):** so sánh không nghiêm ngặt.

Overload **content().json(expectedJson)** mặc định sử dụng chế độ không nghiêm ngặt. Khi đọc test, truyền rõ tham số boolean thường giúp thể hiện ý định tốt hơn.

Ví dụ endpoint trả về danh sách đơn hàng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class OrderControllerTests {

    // Giả sử mockMvc đã được cấu hình trong test class.

    @Test
    void returnsOrdersInTheContractualOrder() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(content().json("""
                        [
                          {"id": 101, "status": "NEW"},
                          {"id": 102, "status": "PAID"}
                        ]
                        """, true));
    }
}
~~~

Với **true**, test yêu cầu cấu trúc JSON khớp chính xác theo chế độ strict: các array phải có thứ tự phần tử tương ứng và object không được có thuộc tính thừa ngoài dữ liệu mong đợi. Nếu response đảo vị trí hai đơn hàng hoặc thêm một trường không có trong JSON kỳ vọng, phép so sánh sẽ thất bại.

Nếu API chỉ cam kết trả về tập hợp đơn hàng mà không cam kết thứ tự, dùng chế độ không nghiêm ngặt:

~~~java
@Test
void returnsTheOrdersWithoutDependingOnTheirOrder() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().json("""
                    [
                      {"id": 101, "status": "NEW"},
                      {"id": 102, "status": "PAID"}
                    ]
                    """, false));
}
~~~

Chế độ không nghiêm ngặt cho phép các phần tử array xuất hiện theo thứ tự khác và cho phép response có thêm thuộc tính object. Các trường được nêu trong JSON kỳ vọng vẫn phải được tìm thấy với giá trị phù hợp. Do đó, test trên không phụ thuộc thứ tự hai đơn hàng, nhưng vẫn kiểm tra id và status của từng đơn.

## Chính xác điều gì thay đổi giữa hai chế độ?

| Đặc điểm | Nghiêm ngặt (true) | Không nghiêm ngặt (false) |
| --- | --- | --- |
| Thứ tự thuộc tính trong object | Không quan trọng | Không quan trọng |
| Thứ tự phần tử trong array | Phải khớp | Có thể khác |
| Thuộc tính object phát sinh thêm trong response | Bị từ chối | Được chấp nhận |
| Trường kỳ vọng bị thiếu hoặc có giá trị sai | Thất bại | Thất bại |

Điểm dễ nhầm là “strict” không có nghĩa JSON phải giống hệt từng ký tự. Thứ tự thuộc tính object vẫn không được xem là thứ tự có ý nghĩa. Strict tập trung vào việc cấu trúc mong đợi phải khớp và thứ tự array phải được giữ nguyên.

Ví dụ, với JSON kỳ vọng:

~~~json
[
  {"id": 101, "status": "NEW"},
  {"id": 102, "status": "PAID"}
]
~~~

Các tình huống sau có kết quả như vậy:

| JSON thực tế | Nghiêm ngặt | Không nghiêm ngặt | Lý do |
| --- | --- | --- | --- |
| Object đổi thứ tự id và status, array giữ nguyên | Đạt | Đạt | Thứ tự key trong object không có ý nghĩa |
| Hai phần tử array đổi vị trí | Không đạt | Đạt | Chỉ chế độ nghiêm ngặt yêu cầu thứ tự array |
| Một object có thêm createdAt | Không đạt | Đạt | Chế độ không nghiêm ngặt chấp nhận thuộc tính bổ sung |
| Thiếu status hoặc id | Không đạt | Không đạt | Dữ liệu kỳ vọng không được đáp ứng |
| status có giá trị khác | Không đạt | Không đạt | Giá trị nghiệp vụ không khớp |

Hãy chọn chế độ theo hợp đồng API. Nếu thứ tự danh sách có ý nghĩa, ví dụ endpoint trả về kết quả đã sắp xếp theo thời gian hoặc độ ưu tiên, nên kiểm tra nghiêm ngặt. Nếu API chỉ trả về một tập hợp và không cam kết thứ tự, kiểm tra không nghiêm ngặt giúp test tránh phụ thuộc vào thứ tự không ổn định của truy vấn hoặc nguồn dữ liệu.

## Khi chỉ muốn bỏ qua thứ tự array

Tham số boolean của **content().json(expectedJson, strict)** chọn hai chế độ phổ biến, nhưng đồng thời điều khiển cả hai chính sách: thứ tự array và thuộc tính bổ sung. Có trường hợp yêu cầu chỉ bỏ qua thứ tự array nhưng vẫn muốn phát hiện thuộc tính object không được khai báo trong JSON kỳ vọng.

JSONAssert cung cấp bốn chế độ so sánh để tách hai lựa chọn này:

| Chế độ JSONAssert | Thứ tự array | Thuộc tính bổ sung |
| --- | --- | --- |
| STRICT | Nghiêm ngặt | Không cho phép |
| LENIENT | Không nghiêm ngặt | Cho phép |
| NON_EXTENSIBLE | Không nghiêm ngặt | Không cho phép |
| STRICT_ORDER | Nghiêm ngặt | Cho phép |

Nếu cần chế độ NON_EXTENSIBLE, có thể lấy response từ MockMvc rồi gọi JSONAssert trực tiếp:

~~~java
import org.skyscreamer.jsonassert.JSONAssert;
import org.skyscreamer.jsonassert.JSONCompareMode;
import org.springframework.test.web.servlet.MvcResult;

@Test
void ignoresArrayOrderButRejectsUnexpectedObjectFields() throws Exception {
    MvcResult result = mockMvc.perform(get("/api/orders")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andReturn();

    String expectedJson = """
            [
              {"id": 101, "status": "NEW"},
              {"id": 102, "status": "PAID"}
            ]
            """;

    String actualJson = result.getResponse().getContentAsString();

    JSONAssert.assertEquals(
            expectedJson,
            actualJson,
            JSONCompareMode.NON_EXTENSIBLE
    );
}
~~~

**NON_EXTENSIBLE** bỏ qua thứ tự phần tử array nhưng vẫn yêu cầu các object không có trường bổ sung. Ngược lại, **STRICT_ORDER** giữ thứ tự array nhưng cho phép thuộc tính object bổ sung. Cả hai chế độ này hữu ích khi hợp đồng API cần kết hợp chính sách cấu trúc và thứ tự khác với hai lựa chọn strict/lenient mặc định.

Đoạn code dùng API của thư viện JSONAssert (org.skyscreamer:jsonassert). Dependency này thường có sẵn qua bộ dependency kiểm thử Spring Boot. Nếu dự án tự khai báo dependency kiểm thử tối giản, cần bảo đảm JSONAssert nằm trên test classpath trước khi dùng import trên.

## Kiểm tra thứ tự một phần bằng JsonPath

Không phải test nào cũng cần so sánh toàn bộ response. Nếu mục tiêu là xác nhận một vài phần tử quan trọng nằm ở đúng vị trí, có thể dùng jsonPath:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@Test
void placesTheHighestPriorityOrderFirst() throws Exception {
    mockMvc.perform(get("/api/orders/priority"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(101))
            .andExpect(jsonPath("$[1].id").value(102));
}
~~~

Biểu thức **$[0]** và **$[1]** truy cập phần tử đầu tiên và thứ hai của array gốc. Cách này xác nhận vị trí của các id được quan tâm, đồng thời cho phép response có thêm thuộc tính mà test không cần quan tâm.

JsonPath phù hợp khi chỉ cần kiểm tra một phần cấu trúc hoặc một số giá trị. Nếu cần xác nhận toàn bộ JSON, kể cả các trường lồng nhau, nên dùng **content().json(...)** hoặc JSONAssert. Nhiều assertion JsonPath rời rạc có thể bỏ sót trường bị thiếu hoặc dữ liệu ngoài dự kiến mà một phép so sánh JSON đầy đủ sẽ phát hiện.

## Kết hợp so sánh JSON với các assertion HTTP khác

So sánh JSON chỉ kiểm tra response body. Nó không thay thế việc kiểm tra status code, content type hoặc header. Một test MVC thường nên xác nhận các khía cạnh này riêng biệt:

~~~java
mockMvc.perform(get("/api/orders/101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "id": 101,
                  "status": "NEW"
                }
                """, true));
~~~

Mỗi assertion có một mục đích:

- **status().isOk()** xác nhận HTTP status.
- **contentTypeCompatibleWith(...)** xác nhận response có media type tương thích JSON, kể cả khi header có thêm charset.
- **content().json(...)** xác nhận cấu trúc và dữ liệu body theo chế độ đã chọn.

Nếu API trả về lỗi có cấu trúc JSON, vẫn có thể dùng cùng cách kiểm tra. Chỉ cần chọn status mong đợi và JSON body tương ứng:

~~~java
mockMvc.perform(get("/api/orders/999999"))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "code": "ORDER_NOT_FOUND",
                  "message": "Order was not found"
                }
                """, true));
~~~

## Các lỗi thường gặp khi chọn chế độ

### Dùng chế độ không nghiêm ngặt cho API có thứ tự nghiệp vụ

Một endpoint có thể cam kết sắp xếp đơn hàng mới nhất trước, kết quả tìm kiếm theo điểm số giảm dần hoặc các bước xử lý theo thứ tự. Nếu dùng **false**, test có thể vẫn đạt dù response vi phạm cam kết sắp xếp. Khi thứ tự là một phần của API contract, hãy dùng **true** hoặc assertion JsonPath tại các vị trí cần thiết.

### Dùng chế độ nghiêm ngặt khi API cho phép mở rộng response

API có thể bổ sung trường metadata mà không làm thay đổi các trường hiện tại. Nếu test luôn dùng **true**, một trường bổ sung hợp lệ cũng khiến test thất bại. Khi hợp đồng cho phép mở rộng object và không cam kết thứ tự array, **false** phù hợp hơn.

### Cho rằng đổi thứ tự key object là lỗi

JSON object không mang thứ tự thuộc tính. Nếu thứ tự key thay đổi nhưng tên và giá trị không đổi, phép so sánh JSON theo cấu trúc vẫn phải đạt. Nếu một hệ thống yêu cầu định dạng chuỗi có thứ tự cố định vì lý do đặc biệt, đó là một yêu cầu serialization riêng và cần được kiểm tra như chuỗi hoặc bằng serializer contract tương ứng.

### Nhầm thứ tự array với thứ tự object

**strict=true** quan tâm thứ tự array, không bắt buộc serializer phải ghi id trước status. Hãy xác định rõ cấu trúc nào là array và cấu trúc nào là object trước khi chọn chế độ.

### Chỉ kiểm tra body mà quên status và content type

Một response có JSON body đúng nhưng status code sai vẫn là response sai. Hãy kết hợp assertion body với status và media type theo hợp đồng endpoint.

### Dùng JsonPath cho mọi trường hợp

JsonPath rất tốt để kiểm tra vị trí hoặc giá trị cụ thể, nhưng một số lượng lớn assertion rời rạc có thể làm test dài và bỏ sót trường ngoài dự kiến. Dùng so sánh JSON đầy đủ khi mục tiêu là xác nhận toàn bộ payload.

## Quy trình chọn cách so sánh

1. Xác định endpoint có cam kết thứ tự phần tử array hay không.
2. Xác định response có được phép bổ sung thuộc tính object mà không phá vỡ hợp đồng hay không.
3. Nếu cần cả hai chính sách phổ biến, dùng **content().json(expected, true)** cho strict hoặc **content().json(expected, false)** cho lenient.
4. Nếu cần bỏ qua thứ tự array nhưng vẫn từ chối thuộc tính bổ sung, dùng **JSONCompareMode.NON_EXTENSIBLE**; nếu cần giữ thứ tự nhưng cho phép thuộc tính bổ sung, dùng **JSONCompareMode.STRICT_ORDER**.
5. Nếu chỉ cần kiểm tra một số vị trí hoặc trường cụ thể, dùng **jsonPath** để diễn đạt trực tiếp điều kiện.
6. Kết hợp kiểm tra JSON với HTTP status và content type để xác nhận đầy đủ kết quả MVC.

Một test tốt phản ánh đúng cam kết của endpoint. Chế độ nghiêm ngặt giúp phát hiện thay đổi về thứ tự và cấu trúc ngoài dự kiến; chế độ không nghiêm ngặt phù hợp với dữ liệu không có thứ tự cam kết và response có thể mở rộng. Khi hai chính sách cần được điều khiển độc lập, JSONAssert hoặc JsonPath cho phép diễn đạt chính xác yêu cầu mà test cần bảo vệ.
