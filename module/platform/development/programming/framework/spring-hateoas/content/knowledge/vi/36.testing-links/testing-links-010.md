# Golden response test cho Spring HATEOAS

Một API có hypermedia không chỉ trả dữ liệu. Representation còn chứa link relation, URI, embedded resource, metadata phân trang và đôi khi cả affordance. Khi một thay đổi serializer hoặc assembler vô tình làm mất link **self**, đổi relation hoặc thay cấu trúc HAL, unit test cho service vẫn có thể pass dù client thực tế bị hỏng.

**Golden response test** kiểm tra representation HTTP hoàn chỉnh bằng cách so sánh response hiện tại với một response chuẩn đã được duyệt. Với Spring HATEOAS, cách làm này giúp phát hiện thay đổi ngoài ý muốn trong HAL JSON, đồng thời giữ được contract mà client đang sử dụng.

Bài này xây dựng golden response test cho endpoint **GET /orders/{id}** bằng MockMvc và JSONAssert, sau đó mở rộng sang collection, pagination, link relation, content negotiation và các response phụ thuộc quyền truy cập.

## 1. Golden response test là gì?

Golden response test còn được gọi là snapshot test hoặc approval test. Test lưu một response mẫu đã được xác nhận là đúng. Mỗi lần chạy, ứng dụng tạo response mới rồi so sánh nó với fixture chuẩn.

Ví dụ response chuẩn cho một đơn hàng:

~~~json
{
  "id": 42,
  "status": "PAID",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.test:8443/orders/42"
    },
    "customer": {
      "href": "https://api.example.test:8443/customers/7"
    }
  }
}
~~~

Golden test kiểm tra response hiện tại có cùng cấu trúc và giá trị contract với fixture hay không. Nếu assembler vô tình bỏ link customer, đổi relation self, đổi kiểu dữ liệu total hoặc thêm field không mong muốn, test sẽ báo khác biệt.

Golden response test phù hợp để bảo vệ contract serialization. Nó không thay thế unit test cho nghiệp vụ, test authorization hoặc test từng link relation. Nên kết hợp các cấp test để vừa phát hiện thay đổi toàn response, vừa xác định rõ nguyên nhân khi có lỗi.

## 2. Vì sao hypermedia cần golden response test?

Một response HATEOAS có nhiều phần mà client có thể phụ thuộc:

- Field dữ liệu như id, status, total.
- Link relation như self, next, search, customer.
- URI đích trong thuộc tính href.
- Cấu trúc _embedded của collection.
- Metadata phân trang trong page.
- Metadata affordance hoặc template khi media type hỗ trợ.

Một thay đổi tưởng như nhỏ có thể phá client. Ví dụ:

| Thay đổi ngoài ý muốn | Ảnh hưởng tới client |
|---|---|
| Xóa link self | Client mất URI chuẩn để quay lại resource |
| Đổi relation customer thành client | Client không tìm thấy link theo relation cũ |
| Đổi href từ /customers/7 sang URI nội bộ | Client không thể truy cập tài nguyên |
| Đổi _embedded.orders thành _embedded.orderList | Client không tìm thấy collection |
| Bỏ link next | Client không thể tiếp tục duyệt trang |
| Đổi page.totalElements thành field khác | Client mất metadata phân trang |
| Serialize số tiền thành chuỗi | Client có thể không parse được kiểu dữ liệu cũ |

Golden response test bảo vệ toàn representation. Các test focused vẫn cần thiết để diễn đạt rõ các yêu cầu quan trọng như link self phải trỏ đúng item hoặc next phải giữ filter.

## 3. Golden fixture nên được lưu ở đâu?

Lưu response chuẩn trong test resources, tách khỏi source code production.

Một cấu trúc thường dùng:

~~~text
src/
└── test/
    ├── java/
    │   └── com/example/orders/
    │       └── OrderControllerGoldenTest.java
    └── resources/
        └── golden/
            └── orders/
                ├── order-42.hal.json
                ├── orders-page-0.hal.json
                └── orders-empty.hal.json
~~~

Tên fixture nên thể hiện endpoint và tình huống. Ví dụ **order-42.hal.json** mô tả response chi tiết một đơn hàng; **orders-page-0.hal.json** mô tả trang đầu; **orders-empty.hal.json** mô tả kết quả tìm kiếm rỗng.

Không lưu fixture ở thư mục production resources. Fixture là dữ liệu kiểm thử và nên được quản lý cùng test để reviewer thấy rõ thay đổi contract trong pull request.

Với response phụ thuộc vai trò hoặc media type, tạo fixture riêng có tên thể hiện điều kiện:

~~~text
golden/
├── orders/
│   ├── order-42-anonymous.hal.json
│   ├── order-42-customer.hal.json
│   └── order-42-admin.hal.json
└── forms/
    └── order-search.hal-forms.json
~~~

Chỉ tạo nhiều fixture khi các response thực sự có contract khác nhau. Không nhân bản fixture cho những trường hợp chỉ khác dữ liệu không có ý nghĩa với contract.

## 4. Chuẩn bị dữ liệu kiểm thử ổn định

Golden test chỉ đáng tin khi đầu vào có thể tái tạo. Không nên để response phụ thuộc vào dữ liệu ngẫu nhiên hoặc thời gian hiện tại.

Một fixture đơn hàng nên có dữ liệu cố định:

~~~java
Order order = new Order(
    42L,
    OrderStatus.PAID,
    new BigDecimal("1250000"),
    Instant.parse("2026-01-15T08:30:00Z"),
    new Customer(7L, "Nguyen Van An")
);
~~~

Các giá trị như ID, trạng thái, số tiền và thời gian phải được kiểm soát. Nếu service tạo timestamp bằng clock hiện tại, hãy inject Clock và dùng Clock.fixed(...) trong test.

Ví dụ:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T08:30:00Z"),
    ZoneOffset.UTC
);
~~~

Với repository hoặc service mock, cấu hình trả về cùng một object cho mỗi lần chạy. Với integration test dùng database test, tạo dữ liệu fixture theo script hoặc factory có giá trị cố định.

Tránh đưa vào golden response:

- UUID ngẫu nhiên tạo mới mỗi lần test.
- Timestamp lấy từ Instant.now().
- Request ID hoặc trace ID thay đổi theo lần chạy.
- Dữ liệu phụ thuộc thứ tự không được quy định.
- Giá trị host hoặc port ngẫu nhiên nếu link được serialize thành absolute URI.

Nếu một field thay đổi là một phần contract và cần được kiểm tra, hãy làm cho nó xác định bằng clock, fixture hoặc cấu hình test thay vì bỏ qua field đó.

## 5. Ổn định host, scheme và port trong link

Spring HATEOAS có thể tạo absolute link dựa trên HTTP request hiện tại. Vì vậy, response có thể chứa host, scheme và port.

Nếu test chạy trên môi trường khác nhau, link có thể thay đổi:

~~~text
http://localhost/orders/42
https://test-host/orders/42
https://api.example.test:8443/orders/42
~~~

Nếu href là một phần contract, hãy cố định request context để tạo URI nhất quán. Với MockMvc, có thể dùng request post-processor:

~~~java
MockHttpServletRequestBuilder request = get("/orders/42")
    .with(servletRequest -> {
        servletRequest.setScheme("https");
        servletRequest.setServerName("api.example.test");
        servletRequest.setServerPort(8443);
        return servletRequest;
    })
    .accept(MediaTypes.HAL_JSON);
~~~

Sau đó fixture có thể dùng host chuẩn:

~~~text
https://api.example.test:8443/orders/42
~~~

Nếu API contract cố ý dùng relative URI, fixture nên chứa relative URI và test cần cấu hình link generation tương ứng. Không nên chuẩn hóa hoặc bỏ qua toàn bộ href chỉ để test pass, vì khi đó golden test không còn bảo vệ được link.

Trong môi trường có reverse proxy, forwarded headers có thể ảnh hưởng URI được tạo. Hãy có test riêng xác nhận scheme, host và prefix bên ngoài mà client thực sự nhìn thấy.

## 6. Tạo golden fixture cho một HAL response

Ví dụ file **src/test/resources/golden/orders/order-42.hal.json**:

~~~json
{
  "id": 42,
  "status": "PAID",
  "total": 1250000,
  "createdAt": "2026-01-15T08:30:00Z",
  "_links": {
    "self": {
      "href": "https://api.example.test:8443/orders/42"
    },
    "customer": {
      "href": "https://api.example.test:8443/customers/7"
    }
  }
}
~~~

Fixture chỉ lưu field công khai của representation. Không đưa dữ liệu nội bộ như entity version, database key không công bố hoặc thông tin debug vào fixture.

Cấu trúc JSON của fixture cần khớp với media type được endpoint trả về. Nếu endpoint trả HAL JSON, test phải gửi **Accept: application/hal+json** và kiểm tra content type tương thích với HAL.

## 7. So sánh JSON bằng JSONAssert

Không nên so sánh response JSON bằng chuỗi thuần:

~~~java
assertThat(actual).isEqualTo(expected);
~~~

So sánh chuỗi nhạy cảm với khoảng trắng, xuống dòng và thứ tự field JSON. Hai JSON object có thể tương đương về cấu trúc nhưng khác thứ tự key.

JSONAssert so sánh cấu trúc JSON. Với **JSONCompareMode.STRICT**, test yêu cầu các field khớp, không cho phép field thừa và giữ thứ tự phần tử trong array; thứ tự key của JSON object không phải yếu tố quyết định.

Ví dụ:

~~~java
JSONAssert.assertEquals(
    expectedJson,
    actualJson,
    JSONCompareMode.STRICT
);
~~~

Chế độ strict phù hợp khi fixture đại diện cho contract response đầy đủ. Nếu một phần response được phép mở rộng, hãy dùng custom comparator hoặc các assertion focused cho đúng field đó thay vì chuyển toàn bộ test sang chế độ quá dễ dãi.

## 8. Viết golden response test bằng MockMvc

MockMvc chạy request qua Spring MVC pipeline trong môi trường test. Nó có thể kiểm tra controller, assembler, message converter và content negotiation mà không cần mở cổng HTTP thật.

Ví dụ test:

~~~java
import static java.nio.charset.StandardCharsets.UTF_8;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.InputStream;
import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.skyscreamer.jsonassert.JSONAssert;
import org.skyscreamer.jsonassert.JSONCompareMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.ClassPathResource;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.util.StreamUtils;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerGoldenTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsGoldenHalRepresentationForOrder42() throws Exception {
        when(orderService.getById(42L)).thenReturn(orderFixture());

        MvcResult result = mockMvc.perform(
                get("/orders/42")
                    .with(request -> {
                        request.setScheme("https");
                        request.setServerName("api.example.test");
                        request.setServerPort(8443);
                        return request;
                    })
                    .accept(MediaTypes.HAL_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON
            ))
            .andReturn();

        String actualJson = result.getResponse()
            .getContentAsString(UTF_8);

        ClassPathResource fixture = new ClassPathResource(
            "golden/orders/order-42.hal.json"
        );

        String expectedJson;
        try (InputStream input = fixture.getInputStream()) {
            expectedJson = StreamUtils.copyToString(input, UTF_8);
        }

        JSONAssert.assertEquals(
            expectedJson,
            actualJson,
            JSONCompareMode.STRICT
        );
    }

    private Order orderFixture() {
        return new Order(
            42L,
            OrderStatus.PAID,
            new BigDecimal("1250000"),
            Instant.parse("2026-01-15T08:30:00Z"),
            new Customer(7L, "Nguyen Van An")
        );
    }
}
~~~

Trong test slice, cần đăng ký controller, assembler và các dependency liên quan bằng cấu hình test. Nếu mục tiêu là kiểm tra cả auto-configuration Spring Boot, có thể dùng **@SpringBootTest** kết hợp **@AutoConfigureMockMvc**.

Golden test trên xác nhận response hoàn chỉnh. Khi một field hoặc link thay đổi, JSONAssert chỉ ra vị trí khác biệt để reviewer đánh giá thay đổi đó có chủ đích hay không.

## 9. Kết hợp golden test với assertion theo link relation

Golden fixture tốt cho việc phát hiện thay đổi toàn response, nhưng assertion riêng giúp mô tả rõ hành vi hypermedia quan trọng.

Ví dụ:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value("https://api.example.test:8443/orders/42"))
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Một số điều cần kiểm tra:

- Link self trỏ đúng resource hiện tại.
- Link relation tới customer chỉ xuất hiện khi đơn hàng có customer.
- Link payment chỉ xuất hiện khi workflow cho phép.
- Link cancel không xuất hiện khi đơn đã hoàn tất.
- Link search được đánh dấu templated: true nếu href chứa URI template.
- Link next chỉ xuất hiện khi còn trang tiếp theo.

Các assertion này kiểm tra semantics. Một golden fixture có thể cho biết response thay đổi, còn assertion relation giúp giải thích vì sao thay đổi đó không hợp lệ.

## 10. Golden test cho collection response

Collection HAL có thêm _embedded và link cấp collection. Ví dụ:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "https://api.example.test:8443/orders/42"
          }
        }
      },
      {
        "id": 43,
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.test:8443/orders/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test:8443/orders"
    },
    "search": {
      "href": "https://api.example.test:8443/orders{?status,page,size}",
      "templated": true
    }
  }
}
~~~

Golden test collection cần kiểm tra cả cấu trúc _embedded và link ở cấp collection. Không nhầm link self của từng item với link self của collection.

Nếu thứ tự item là một phần contract, fixture nên giữ thứ tự và so sánh array ở chế độ strict. Nếu thứ tự không được quy định, test có thể so sánh theo ID hoặc dùng comparator phù hợp; không nên vô tình bỏ qua thứ tự khi API có cam kết sort.

## 11. Golden test cho PagedModel

Paged response có thêm metadata phân trang và các link điều hướng.

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "https://api.example.test:8443/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test:8443/orders?page=0&size=1&sort=id,asc"
    },
    "next": {
      "href": "https://api.example.test:8443/orders?page=1&size=1&sort=id,asc"
    }
  },
  "page": {
    "size": 1,
    "totalElements": 2,
    "totalPages": 2,
    "number": 0
  }
}
~~~

Fixture phải dùng tập dữ liệu cố định để totalElements, totalPages và link next không thay đổi giữa các lần chạy.

Các assertion quan trọng:

~~~java
.andExpect(jsonPath("$.page.number").value(0))
.andExpect(jsonPath("$.page.size").value(1))
.andExpect(jsonPath("$.page.totalElements").value(2))
.andExpect(jsonPath("$._links.next.href").exists());
~~~

Với trang cuối, cần fixture hoặc focused test xác nhận next không còn tồn tại. Với trang đầu, kiểm tra hành vi prev theo contract của API. Nếu endpoint có filter và sort, link điều hướng phải giữ những query parameter đó.

## 12. Golden test cho search template và affordance

Search link là một phần contract hypermedia quan trọng. Ví dụ:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test:8443/orders{?status,customer,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Test nên xác nhận cả relation, URI template và metadata:

~~~java
mockMvc.perform(
        get("/orders")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.href").exists())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(org.hamcrest.Matchers.containsString("{?status")));
~~~

Nếu API hỗ trợ HAL-FORMS, template có thể được serialize trong _templates. Golden fixture HAL-FORMS nên được tách riêng khỏi HAL JSON vì cấu trúc representation và media type khác nhau.

Không nên chỉ kiểm tra href có chứa một chuỗi bất kỳ. Hãy xác nhận các biến quan trọng mà client cần dùng và bảo đảm link có relation đúng.

## 13. Xử lý các giá trị động trong golden response

Một số field có thể thay đổi theo request hoặc môi trường:

- Absolute URI chứa host và port.
- Timestamp do hệ thống tạo.
- ID sinh tự động.
- Correlation ID.
- Giá trị phân trang phụ thuộc dữ liệu.
- Link chỉ xuất hiện với một role hoặc tenant cụ thể.

Có ba chiến lược:

**1. Cố định đầu vào và môi trường.** Đây là lựa chọn ưu tiên. Dùng ID cố định, clock cố định, host/port cố định, database fixture và principal xác định.

**2. Chuẩn hóa đúng field không thuộc contract.** Nếu một giá trị thực sự không phải contract, có thể parse JSON rồi thay giá trị đó bằng placeholder trước khi so sánh. Chỉ chuẩn hóa field cụ thể; không xóa toàn bộ _links hoặc href.

**3. Dùng custom comparator.** Khi một field cần được kiểm tra theo quy tắc thay vì giá trị chính xác, custom comparator có thể xác nhận dạng URI, timestamp hoặc pattern. Comparator phải vẫn bắt được thay đổi contract có ý nghĩa.

Ví dụ, nếu correlation ID không phải nội dung API công bố cho client, có thể loại riêng field đó khỏi phép so sánh. Nhưng nếu href thay đổi từ public host sang internal host, đó là lỗi contract cần phát hiện, không phải biến động nên bỏ qua.

## 14. Golden response theo quyền người dùng

Link có thể thay đổi theo authorization. Ví dụ:

- Customer chỉ thấy link self, customer và payment.
- Support agent thấy thêm link refund.
- Administrator thấy thêm link audit.

Nếu response khác nhau theo role, hãy tạo test với principal xác định và fixture riêng cho mỗi contract cần bảo vệ.

~~~java
mockMvc.perform(
        get("/orders/42")
            .with(user("support-agent").roles("SUPPORT"))
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.refund.href").exists());
~~~

Test cho customer có thể xác nhận link refund không được công bố nếu contract yêu cầu ẩn capability đó:

~~~java
.andExpect(jsonPath("$._links.refund").doesNotExist());
~~~

Ẩn link không thay thế kiểm tra quyền ở endpoint đích. Golden response chỉ kiểm tra representation được trả cho principal cụ thể; cần test authorization riêng để xác nhận người dùng không thể gọi trực tiếp hành động không được phép.

## 15. Golden test cho content negotiation

Một endpoint có thể hỗ trợ nhiều media type. Test phải gửi đúng Accept header và xác nhận Content-Type của response.

Ví dụ HAL:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON
    ));
~~~

Nếu endpoint hỗ trợ thêm representation khác, hãy tạo test riêng cho từng media type. Không dùng chung fixture HAL cho response JSON thuần hoặc HAL-FORMS.

Nếu client gửi media type không được hỗ trợ, test có thể xác nhận 406 Not Acceptable theo cấu hình content negotiation của ứng dụng.

## 16. Khi nào dùng golden test, khi nào dùng focused test?

Hai dạng test phục vụ mục đích khác nhau:

| Tiêu chí | Golden response | Focused assertion |
|---|---|---|
| Phạm vi | Toàn representation | Một field, link hoặc quy tắc |
| Phát hiện field bị thêm/xóa | Có | Chỉ khi có assertion |
| Phát hiện link relation thay đổi | Có | Có nếu test đúng relation |
| Giải thích mục đích assertion | Thường ít cụ thể | Rõ ràng |
| Bảo trì fixture | Cần cập nhật khi contract thay đổi | Thường ít công việc hơn |
| Phù hợp | Regression contract, serialization | Quy tắc nghiệp vụ và hypermedia cụ thể |

Một chiến lược cân bằng là có golden test cho một số response đại diện và focused test cho các điều kiện quan trọng. Không cần snapshot mọi endpoint và mọi tổ hợp filter; số lượng fixture quá lớn làm việc cập nhật trở nên tốn kém.

## 17. Cập nhật golden fixture khi contract thay đổi

Khi golden test thất bại, không nên tự động chép response mới thành fixture. Hãy xác định nguyên nhân trước:

1. Đọc diff để biết field, relation hoặc href nào đã thay đổi.
2. Kiểm tra thay đổi có được yêu cầu trong task hoặc thiết kế API không.
3. Xác nhận thay đổi có tương thích với client hiện tại không.
4. Cập nhật tài liệu contract và focused test nếu semantics thay đổi.
5. Chỉ cập nhật fixture sau khi reviewer chấp thuận thay đổi.
6. Chạy lại test để xác nhận fixture mới phản ánh contract đã duyệt.

Một fixture thay đổi cùng code trong cùng pull request giúp reviewer nhìn thấy contract HTTP thay đổi. Không cập nhật fixture chỉ để làm build xanh nếu chưa hiểu vì sao response khác.

Nếu response mới chỉ khác timestamp hoặc host do môi trường test không ổn định, hãy sửa cách tạo dữ liệu hoặc request context để test deterministic thay vì cập nhật fixture theo giá trị ngẫu nhiên.

## 18. Tránh golden test quá mong manh

Golden test có thể trở nên khó bảo trì nếu nó so sánh các chi tiết không có ý nghĩa với client.

Một số cách giảm độ mong manh:

- So sánh JSON theo cấu trúc thay vì chuỗi.
- Giữ fixture nhỏ, chỉ chứa response tiêu biểu.
- Cố định clock, ID, host, port và database state.
- Không đưa stack trace, debug data hoặc request ID vào representation công khai.
- Dùng custom comparator cho đúng field thực sự động.
- Không bỏ qua toàn bộ _links hoặc _embedded.
- Kiểm tra riêng relation và URI quan trọng.
- Giữ thứ tự array khi thứ tự đó là một phần contract.
- Tách fixture theo media type và role khi response thực sự khác nhau.

Không nên dùng một chế độ so sánh quá lỏng cho tất cả fixture. Nếu test cho phép field thừa và thiếu tùy ý, nó có thể bỏ lọt thay đổi phá client.

## 19. Kiểm thử lỗi và response không có link

Golden test không chỉ dành cho response thành công. Có thể lưu fixture cho lỗi theo Problem Details hoặc format lỗi riêng của API, nếu cấu trúc đó là contract công khai.

Các trường hợp đáng kiểm tra:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Item không tồn tại | Status 404 và error representation đúng |
| Không có quyền | Status 403 hoặc chính sách 404, không lộ link bị cấm |
| Collection rỗng | _embedded vắng mặt hoặc rỗng theo serializer contract |
| Trang cuối | Không có link next |
| Hành động không khả dụng | Không công bố affordance hoặc action link |
| Accept không hỗ trợ | Status 406 theo cấu hình |

Không cần tạo fixture cho mọi lỗi kỹ thuật nội bộ. Chỉ golden-test các error representation mà client được kỳ vọng sẽ đọc và xử lý.

## 20. Quy trình xây dựng golden response test

Khi bảo vệ contract Spring HATEOAS bằng golden response test, hãy thực hiện theo trình tự:

1. Chọn một endpoint đại diện và media type cụ thể.
2. Tạo dữ liệu kiểm thử ổn định.
3. Cố định clock, host, scheme và port nếu chúng ảnh hưởng response.
4. Gọi endpoint qua MockMvc với Accept phù hợp.
5. Kiểm tra HTTP status và Content-Type.
6. Đọc response body và fixture JSON từ test resources.
7. So sánh cấu trúc bằng JSONAssert hoặc JSONUnit.
8. Thêm focused assertion cho relation, href, embedded resource và page metadata quan trọng.
9. Tạo fixture riêng cho role hoặc media type nếu contract khác nhau.
10. Review mọi fixture diff trước khi chấp nhận thay đổi.
11. Chạy lại test để xác nhận representation mới ổn định qua nhiều lần thực thi.

Golden response test giúp bảo vệ representation mà client thực sự nhận được. Kết hợp MockMvc, fixture JSON ổn định, so sánh cấu trúc và assertion theo link relation, nhóm test này phát hiện sớm các thay đổi ngoài ý muốn trong dữ liệu, URI và hypermedia controls của Spring HATEOAS.

## Tài liệu tham khảo

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring HATEOAS Reference — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS Reference — Hypermedia support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [JSONAssert — JSON comparison library](https://github.com/skyscreamer/JSONassert)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
