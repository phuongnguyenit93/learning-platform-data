# Định nghĩa nhiều hợp đồng trong cùng tệp Groovy DSL

Trong **Spring Cloud Contract**, mỗi hợp đồng mô tả một tương tác mà **producer** phải thực hiện: một yêu cầu và phản hồi HTTP, hoặc một tình huống gửi/nhận thông điệp. Producer dùng hợp đồng để **sinh kiểm thử xác minh hành vi triển khai**; từ cùng nguồn mô tả, quy trình build tạo **stub** để consumer thử mã gọi thông qua **Stub Runner**. Khi các hành vi có liên quan chặt chẽ, bạn có thể đặt **nhiều hợp đồng trong một tệp Groovy DSL** thay vì tạo một tệp riêng cho từng tình huống.

Bài thuộc chương **Groovy DSL** của mô-đun SPRING_CLOUD_CONTRACT. Trọng tâm không phải viết toàn bộ hệ thống từ đầu mà là hiểu **cách tệp Groovy trả về nhiều đối tượng `Contract`**, tổ chức và đặt tên từng tình huống, tránh các quy tắc khớp request mơ hồ, rồi kiểm tra rằng cả producer test lẫn stub consumer đều phản ánh **đủ tất cả** hợp đồng đã khai báo.

## 1. Khi nào nên đặt nhiều hợp đồng trong một tệp?

Ví dụ **Order Service** cung cấp API `GET /api/orders/{id}`; **Billing Service** cần xử lý ít nhất hai trường hợp: đơn hàng tồn tại và đơn hàng không tồn tại. Hai kỳ vọng có thể được mô tả bằng hai hợp đồng:

| Tình huống | HTTP request | HTTP response | Hành vi consumer cần kiểm tra |
| --- | --- | --- | --- |
| Đơn `42` tồn tại và đã thanh toán | `GET /api/orders/42` | `200`, `{"id":42,"status":"PAID"}` | Đọc đúng `id` và `status`, tiếp tục nghiệp vụ. |
| Đơn `404` không tồn tại | `GET /api/orders/404` | `404`, `{"code":"ORDER_NOT_FOUND","message":"Order does not exist"}` | Nhận diện lỗi nghiệp vụ, không xử lý như đơn hợp lệ. |

Hai trường hợp cùng thuộc hành vi **đọc đơn hàng**, nên có thể đặt trong cùng `get_order.groovy`. Cách tổ chức này hữu ích khi:

- Các tình huống có cùng chủ đề nghiệp vụ và thường được review hoặc cập nhật cùng nhau.
- Muốn người đọc thấy ngay các nhánh thành công và thất bại của cùng một API.
- Số lượng tình huống còn vừa phải và mỗi hợp đồng có tên, request, kết quả rõ ràng.

Khi số tình huống quá lớn, nhiều consumer sở hữu các yêu cầu khác nhau, hoặc mỗi hợp đồng có vòng đời thay đổi độc lập, **tách thành nhiều tệp** thường dễ bảo trì hơn. Spring Cloud Contract hỗ trợ cả hai cách; chọn dựa trên khả năng đọc, review và quản lý phiên bản chứ không dựa vào việc có bắt buộc gom tất cả hợp đồng vào một chỗ hay không.

## 2. Cú pháp cốt lõi: trả về một danh sách các `Contract`

Với hợp đồng Groovy riêng lẻ, tệp thường có dạng:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method 'GET'
        url '/health'
    }
    response {
        status 200
    }
}
```

Để định nghĩa **nhiều hợp đồng trong một tệp**, đặt **các lời gọi `Contract.make { ... }` vào một list Groovy** và để danh sách đó là **giá trị trả về của script**:

```groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'firstScenario'
        request {
            method 'GET'
            url '/first'
        }
        response {
            status 200
        }
    },
    Contract.make {
        name 'secondScenario'
        request {
            method 'GET'
            url '/second'
        }
        response {
            status 404
        }
    }
]
```

Chú ý bốn điểm:

1. Cặp `[ ... ]` bên ngoài là **list Groovy**, không phải phần thân của một `Contract.make`.
2. **Mỗi phần tử** là một lời gọi `Contract.make` độc lập, có `request` và `response` riêng.
3. Các phần tử được ngăn bằng dấu phẩy `,`; dấu đóng `]` kết thúc danh sách.
4. Toàn bộ danh sách là **biểu thức cuối** của script, để quá trình nạp hợp đồng nhận được tập các đối tượng `Contract`.

Về ý nghĩa, tệp trả về một **`List<Contract>`**. Không tạo hai lời gọi `Contract.make` rời rạc rồi mặc nhiên cho rằng công cụ sẽ gom chúng: với một Groovy script, giá trị được trả về có thể chỉ là **biểu thức cuối cùng**. Cũng không đặt một thao tác trả về giá trị khác, chẳng hạn `println`, sau danh sách.

Thuộc tính `name` cho phép đặt tên tình huống có ý nghĩa và giúp nhận diện kết quả kiểm thử được sinh. **Tên nên duy nhất, ổn định và rõ nghĩa trong phạm vi tập hợp hợp đồng**; cách sinh tên lớp/phương thức cụ thể có thể phụ thuộc cấu hình plugin và phiên bản Spring Cloud Contract.

## 3. Ví dụ đầy đủ: hai trường hợp đọc đơn hàng trong một tệp

Giả sử producer lưu hợp đồng tại:

```text
order-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── orders/
                    └── get_order.groovy
```

Nội dung đầy đủ của `src/test/resources/contracts/orders/get_order.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldGetPaidOrder'
        description 'Đọc đơn hàng tồn tại ở trạng thái PAID'

        request {
            method 'GET'
            url '/api/orders/42'
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body(
                id: 42,
                status: 'PAID'
            )
        }
    },

    Contract.make {
        name 'shouldReturnNotFoundForMissingOrder'
        description 'Đọc đơn hàng không tồn tại trả lỗi nghiệp vụ'

        request {
            method 'GET'
            url '/api/orders/404'
        }

        response {
            status 404
            headers {
                contentType(applicationJson())
            }
            body(
                code: 'ORDER_NOT_FOUND',
                message: 'Order does not exist'
            )
        }
    }
]
```

Ở đây **hai hợp đồng chung một tệp nhưng không chung nội dung**: hợp đồng thứ nhất yêu cầu HTTP `200`, đối tượng `Order` và `PAID`; hợp đồng thứ hai yêu cầu HTTP `404` và payload lỗi. Hai đường dẫn chứa ID khác nhau nên các stub có thể khớp request một cách rõ ràng.

Đặt `name` và `description` riêng cho từng trường hợp giúp reviewer tìm được nguyên nhân khi một producer test thất bại. `description` mô tả ý định nghiệp vụ; `name` là định danh ngắn, nên dùng ký tự phù hợp cho tên kiểm thử được sinh. Không dùng một tên chung cho cả hai vì sẽ khó phân biệt các trường hợp trong báo cáo build.

### 3.1. Nếu muốn có thêm hợp đồng thứ ba

Bạn thêm **một phần tử `Contract.make` nữa** vào cùng list, phân cách bằng dấu phẩy. Ví dụ:

```groovy
// Thêm như một phần tử mới bên trong danh sách đang có.
Contract.make {
    name 'shouldGetPendingOrder'
    request {
        method 'GET'
        url '/api/orders/43'
    }
    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(id: 43, status: 'PENDING')
    }
}
```

Đoạn này chỉ là **phần tử để chèn**, không phải nội dung trọn tệp Groovy. Hãy cập nhật producer trả đúng dữ liệu cho `43`, sau đó chạy lại generated tests. Nếu chỉ thêm hợp đồng mà chưa triển khai hành vi tương ứng, producer test mới **phải thất bại**; đó chính là phản hồi mong muốn của quy trình contract testing.

## 4. Mỗi hợp đồng phải là một tình huống độc lập

Trong cùng một `Contract.make`, bạn thường mô tả **một quan hệ request → response cụ thể**. Không nên gộp hai status code hoặc hai phản hồi không tương thích vào cùng một `response` rồi hy vọng Spring Cloud Contract tự chọn theo tình huống.

So sánh:

| Cách tổ chức | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| **Một tệp chứa list hai contract** | Hai tình huống riêng nhưng gần nhau về nghiệp vụ. | Có thể sinh các phép kiểm producer và các stub mapping tương ứng. |
| **Hai tệp, mỗi tệp một contract** | Hai tình huống được quản lý độc lập. | Vẫn sinh kiểm thử và stub tương ứng khi plugin đọc cả hai tệp. |
| **Một contract nhưng ghi hai kết quả không có điều kiện phân biệt** | Kỳ vọng không rõ hoặc mâu thuẫn. | Khó xác minh và dễ làm stub khớp sai. |

Một quy tắc quan trọng: **phân biệt các request**. Nếu hai hợp đồng cùng khớp toàn bộ `method`, `url`, header, query và body nhưng lại mô tả hai response khác nhau, stub server không có đủ dữ kiện để biết cần chọn trường hợp nào. Với WireMock, việc chọn mapping còn phụ thuộc cơ chế ưu tiên/khớp; bài test có thể chạy không như ý định.

Ví dụ cần phân biệt hai hành vi qua query parameter, bạn phải thể hiện sự khác biệt ở **request matcher** của từng hợp đồng. Nếu hành vi khác nhau do trạng thái dữ liệu phía producer nhưng HTTP request hoàn toàn giống nhau, cần thiết kế fixture, định danh dữ liệu hoặc cơ chế mô phỏng rõ ràng để mỗi hợp đồng tạo request có thể phân biệt khi chạy stub. Không tùy tiện thêm hợp đồng mới trùng request rồi dựa vào thứ tự trong list để quyết định response.

## 5. Producer sẽ kiểm thử cả hai hợp đồng ra sao?

Với Spring Cloud Contract Verifier tích hợp trong build của producer, plugin đọc file Groovy và **sinh kiểm thử từ từng contract**. Plugin không chạy file `.groovy` như một JUnit test trực tiếp; nó chuyển định nghĩa contract thành các bài kiểm thử dùng cấu hình dự án (ví dụ MockMvc), rồi Maven/Gradle mới thực thi các bài đó.

Để hai hợp đồng trên đều được producer xác minh, implementation cần xử lý cả hai trường hợp. Một controller Spring MVC minh họa:

```java
package com.acme.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> getOrder(@PathVariable long id) {
        if (id == 42L) {
            return ResponseEntity.ok(new OrderResponse(42L, "PAID"));
        }
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse(
                        "ORDER_NOT_FOUND", "Order does not exist"));
    }

    public record OrderResponse(long id, String status) {}
    public record ErrorResponse(String code, String message) {}
}
```

Đây là implementation **chỉ để minh họa contract**, trong đó `42` luôn tồn tại và `404` không tồn tại. Ứng dụng thật phải dùng service/repository và fixture kiểm thử phù hợp, không hardcode ID nghiệp vụ như trong ví dụ.

Giả sử dự án đã có lớp cơ sở cấu hình MockMvc cho generated tests:

```java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {
    @Autowired MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Ví dụ đoạn cấu hình Maven plugin trong `pom.xml` của producer:

```xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
```

Đây là **đoạn POM**, chưa phải POM hoàn chỉnh. Producer cũng cần starter Spring MVC, test dependencies, Spring Cloud Contract Verifier và các phiên bản Spring Boot/Spring Cloud Contract tương thích. Tham số `spring-cloud-contract.version` phải được định nghĩa trong POM hoặc quản lý plugin phù hợp.

Từ thư mục dự án producer, chạy:

```shell
mvn clean verify
```

Hãy kiểm tra ba kết quả:

1. Plugin đã đọc `get_order.groovy` và sinh code test tương ứng với **cả hai tên hợp đồng**.
2. Báo cáo test cho thấy **cả hai tình huống được thực thi và đạt**; không chỉ dựa vào dòng `BUILD SUCCESS`.
3. Nếu đổi mã producer chỉ trả `200` cho ID `404`, bài test liên quan đến `shouldReturnNotFoundForMissingOrder` thất bại, trong khi test trường hợp `42` có thể vẫn đạt.

Mặc dù hai hợp đồng nằm trong cùng file, chúng **không trở thành một assertion tổng**: bạn cần phân biệt test nào thành công và test nào thất bại. Tên chính xác của file Java, tên lớp và phương thức được sinh có thể thay đổi theo phiên bản plugin hoặc cấu hình đặt tên; kiểm chứng bằng **đầu ra thực của build**.

## 6. Stub sinh từ một list contract và cách consumer sử dụng

Từ **cùng tệp** `get_order.groovy`, quy trình tạo stub HTTP có thể tạo **hai mapping**: một mapping trả `200` khi consumer gọi `/api/orders/42`, mapping còn lại trả `404` với body lỗi khi gọi `/api/orders/404`.

Hai mapping được đóng gói vào artifact stub cùng version của producer, thường có classifier `stubs`. Ví dụ:

```text
com.acme:order-service:1.0.0:stubs
order-service-1.0.0-stubs.jar
```

Khi đã cấu hình plugin build thích hợp, lệnh:

```shell
mvn clean install
```

chạy kiểm thử producer, tạo/đóng gói stub và cài artifact vào Maven local. Nếu producer test thất bại, không nên công bố artifact đó như một bản stub đáng tin cậy. Trong CI, nên đặt bước **publish sau cổng producer test đạt**.

Trong dự án Billing, giả sử đã có `OrderClient` thật với phương thức:

```java
OrderView getOrder(long id);
```

Trong đó `OrderView` là DTO có `id` và `status`, còn client đọc `orders.base-url` từ cấu hình. Bài kiểm thử consumer có thể trỏ URL này sang stub:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.HttpClientErrorException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired OrderClient orderClient;

    @Test
    void shouldReadPaidOrder() {
        OrderView order = orderClient.getOrder(42L);
        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
    }

    @Test
    void shouldReportMissingOrder() {
        assertThatThrownBy(() -> orderClient.getOrder(404L))
            .isInstanceOf(HttpClientErrorException.NotFound.class)
            .hasMessageContaining("404");
    }
}
```

Đây là **minh họa phần test**: dự án consumer cần định nghĩa `OrderClient`, `OrderView`, dependency Stub Runner và client dùng `RestClient.retrieve()` hoặc hành vi ném lỗi tương tự khi nhận HTTP 404. Nếu `OrderClient` tự chuyển 404 thành ngoại lệ nghiệp vụ `OrderNotFoundException`, hãy assert ngoại lệ đó thay cho `HttpClientErrorException.NotFound`. Hai phương thức test tiêu thụ **hai tình huống sinh từ cùng một tệp**.

**Đừng coi bất kỳ HTTP 404 nào từ stub là bằng chứng trường hợp lỗi đã khớp.** WireMock cũng có thể trả `404` khi request **không khớp mapping nào**. Một consumer test chỉ assert `404` có thể đạt giả. Với tình huống lỗi, tốt hơn nên kiểm thêm mã lỗi `ORDER_NOT_FOUND`, message hoặc header có trong **response contract**; hoặc xác minh request đã khớp mapping mong muốn qua cơ chế stub thích hợp.

Để dùng artifact đã **công bố ở Maven repository**, thay `LOCAL` bằng `REMOTE` và cấu hình `repositoryRoot` trỏ tới repository thật, cùng credential an toàn của CI. Không tự sửa các mapping stub ở consumer để làm test xanh; mọi thay đổi hành vi cần đi từ hợp đồng và được producer xác minh trước.

## 7. Tên hợp đồng, đường dẫn và giới hạn tổ chức

Một file chứa nhiều contract vẫn nên dễ tìm và dễ review. Ví dụ:

```text
src/test/resources/contracts/
└── orders/
    ├── get_order.groovy         # 200 và 404 cho thao tác đọc
    ├── create_order.groovy      # Các tình huống tạo đơn
    └── cancel_order.groovy      # Các tình huống hủy đơn
```

Đây là **một cách tổ chức gợi ý**, không phải vị trí duy nhất Spring Cloud Contract cho phép. Tập hợp nhiều hợp đồng trong một file giúp review theo thao tác; các file riêng giúp cô lập những nhóm hành vi ít liên quan. Nếu một tệp trở nên dài đến mức khó tìm từng tình huống, nên tách tệp trong một lần thay đổi có kiểm soát và xác nhận **không làm mất bất kỳ contract nào** khi plugin sinh test/stub.

Quy tắc nên áp dụng:

- **Tên từng contract duy nhất và có nghĩa**: ưu tiên `shouldGetPaidOrder`, `shouldReturnNotFoundForMissingOrder` hơn các tên như `case1` hoặc `test2`.
- **Mỗi request đủ điều kiện nhận diện**: method, URL, query parameter, header hoặc body nên thể hiện sự khác biệt có ý nghĩa của tình huống.
- **Giữ dữ liệu kiểm thử ổn định**: nếu producer test cần đơn `42`, fixture phải chuẩn bị chính xác trạng thái `PAID`.
- **Mỗi hợp đồng thể hiện một kỳ vọng có giá trị với consumer**; đừng tạo danh sách rất dài chỉ để phủ mọi tổ hợp dữ liệu ít quan trọng.
- **Review việc đổi và xóa hợp đồng** như một thay đổi giao diện API; kiểm tra những consumer cũ còn phụ thuộc vào hành vi trước đó.

**Cùng tệp không đồng nghĩa cùng versioning độc lập:** khi phát hành stub artifact, tất cả hợp đồng thuộc build/phiên bản đó được phân phối cùng nhau. Nếu một consumer yêu cầu giữ phản hồi cũ, việc thay hết hợp đồng trong list thành dạng mới có thể khiến producer test và consumer mới đạt, nhưng vẫn phá consumer cũ.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ một hợp đồng được sinh test dù đã viết hai `Contract.make`. | Các lời gọi đứng rời rạc, script không trả về list hoặc kết quả cuối không phải list hợp đồng. | Đặt các contract trong `[ ... ]` và để list là biểu thức cuối của file. |
| Groovy báo lỗi cú pháp khi nạp hợp đồng. | Thiếu dấu phẩy giữa các phần tử, thiếu `}` hoặc `]`, sai dấu nháy. | Kiểm cặp ngoặc và dấu phân cách của từng `Contract.make`. |
| Hai contract tạo stub nhưng request gọi ra phản hồi không mong muốn. | Mapping chồng lấn: cùng method/path và không có điều kiện phân biệt. | Làm rõ matcher của request hoặc thiết kế lại tình huống; không dựa vào thứ tự phần tử trong list. |
| Producer test đạt một tình huống nhưng thất bại tình huống khác. | Producer chỉ thực hiện đúng một trong hai hành vi, fixture chưa đủ dữ liệu. | Xem report theo tên tình huống và sửa implementation/fixture tương ứng. |
| Consumer nhận `404` dù mong đợi `200`. | Client gọi sai path, thiếu header/query, hoặc stub artifact thiếu mapping. | So request thực với mapping của artifact; xác minh version và classifier. |
| Consumer test lỗi `404` vẫn xanh khi gửi sai path. | Assert chỉ kiểm status mà không phân biệt 404 không match với 404 nghiệp vụ. | Kiểm thêm payload `code: ORDER_NOT_FOUND` theo contract hoặc kiểm mapping match. |
| CI consumer không thấy stub mới. | Producer chưa publish artifact, CI dùng version cũ hoặc repository sai. | Kiểm artifact `stubs` đã được phát hành, repository có quyền đọc và version đã ghim. |
| Refactor tách tệp làm thiếu test. | Trong lúc chuyển list thành nhiều file đã bỏ sót tình huống hoặc tạo tên trùng. | So danh sách tên contract trước/sau và số tình huống được sinh, chạy lại producer và consumer tests. |

Khi chẩn đoán, hãy hỏi theo thứ tự: **Groovy script đã trả về bao nhiêu contract?** → **Plugin đã sinh và chạy bao nhiêu producer test?** → **Artifact stub chứa những mapping nào?** → **Consumer gọi mapping nào và thực thi assertion gì?**. Cách đi từ nguồn đặc tả đến hai đầu kiểm thử giúp tìm đúng nguyên nhân thay vì chỉnh sửa một stub chỉ để che lỗi.

## 9. Thực hành: mở rộng một tệp lên ba hợp đồng

Hãy thực hiện bài tập trong dự án producer/consumer thử nghiệm đã cấu hình Spring Cloud Contract:

1. Tạo file `contracts/orders/get_order.groovy` chứa **hai contract** `shouldGetPaidOrder` và `shouldReturnNotFoundForMissingOrder` như mục 3.
2. Viết producer endpoint phản hồi đúng hai tình huống; chạy build và đọc **test report** để xác nhận cả hai test được sinh và thực thi.
3. Cài hoặc phát hành artifact `stubs`, cho consumer chạy qua Stub Runner và kiểm kết quả **200** lẫn **404 với payload lỗi đúng hợp đồng**.
4. Thêm phần tử thứ ba `shouldGetPendingOrder` cho `GET /api/orders/43` trả `200` và `status: PENDING`. Trước khi sửa producer, chạy producer test và quan sát tình huống mới thất bại.
5. Sửa producer và fixture cho đơn `43`; chạy lại producer test để cả ba tình huống đạt. Tạo lại stub artifact, bổ sung consumer test cho `PENDING`.
6. Thử đổi `GET /api/orders/43` trong contract mới thành trùng `/api/orders/42` nhưng giữ response `PENDING`; phân tích vì sao hai mapping cho cùng request có thể tạo phản hồi không xác định theo ý đồ. Hoàn nguyên thay đổi trước khi hoàn tất.

Kết quả cần chứng minh bằng đầu ra build: **một tệp Groovy trả về ba đối tượng contract, ba tình huống được xác minh ở producer và ba tình huống được consumer kiểm thử qua stub tương ứng**. Số lớp Java được sinh có thể phụ thuộc plugin, vì vậy đánh giá theo **từng tình huống được thực thi**, không ép số lớp test phải bằng số contract.

## 10. Câu hỏi tự kiểm tra

- Vì sao đặt hai lời gọi `Contract.make` rời rạc không phải là cách đáng tin cậy để trả về nhiều hợp đồng từ một Groovy script?
- Hai contract trong cùng file cần phân biệt nhau ở đâu nếu dùng chung URL nhưng mong đợi response khác nhau?
- `name` và `description` giúp gì khi một trong các generated producer tests thất bại?
- Một hợp đồng mới cho trạng thái `PENDING` đã được thêm nhưng producer chưa hỗ trợ. Test nào nên thất bại trước khi phát hành stub?
- Khi consumer nhận HTTP 404 từ WireMock, làm cách nào phân biệt lỗi nghiệp vụ được mô tả trong contract với request không khớp mapping?
- Nếu producer và consumer mới đều đạt kiểm thử sau khi xóa một hợp đồng cũ, còn rủi ro gì với consumer đang chạy phiên bản cũ?

**Ghi nhớ:** trong Spring Cloud Contract Groovy DSL, **nhiều hợp đồng trong một tệp = một script trả về danh sách các `Contract.make { ... }` độc lập**. Mỗi contract cần tên rõ ràng, request khớp không mơ hồ và hành vi producer kiểm thử được. Khi build producer xác minh đầy đủ các tình huống trước khi phát hành stub, consumer có thể dùng **Stub Runner** để kiểm thử mã gọi của mình với đúng tập hành vi đã cam kết.
