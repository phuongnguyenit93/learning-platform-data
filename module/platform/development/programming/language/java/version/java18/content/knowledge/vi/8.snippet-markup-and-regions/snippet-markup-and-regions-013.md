# Region lồng nhau hoặc chồng lấn: đặt tên và xác định điểm kết thúc rõ ràng

## Mục tiêu bài học

Trong Javadoc snippet, region xác định một khoảng dòng để markup action tác động hoặc để external snippet trích một phần file. Khi chỉ có một vùng đơn giản, marker không tên có thể đủ. Nhưng khi các vùng lồng nhau hoặc chồng lấn, người viết cần biết **vùng nào đang mở, vùng nào được đóng và phần dòng nào thuộc từng vùng**.

Cách rõ ràng nhất cho cấu trúc phức tạp là đặt tên riêng cho từng region và đóng bằng marker tường minh `@end region="tên"`. Tên region cho phép Javadoc ghép đúng điểm bắt đầu với điểm kết thúc, kể cả khi các vùng chồng lấn và kết thúc không theo thứ tự mở.

Cơ chế snippet được giới thiệu trong Java 18 qua JEP 413 và vẫn được hỗ trợ trong JDK hiện đại. Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Module khám phá các thay đổi Java 18 còn hữu ích trên JDK hiện đại, trong đó có UTF-8 mặc định, Simple Web Server và snippet trong Javadoc; bài này tập trung vào cách tổ chức region để tài liệu API chọn và trình bày đúng phần mã cần thiết.

Sau bài học, bạn có thể:

- Phân biệt region lồng nhau với region chồng lấn.
- Dùng tên riêng để theo dõi nhiều region cùng mở.
- Đóng đúng region bằng `@end region="name"`.
- Giải thích vì sao marker không tên chỉ phù hợp với cấu trúc đóng theo thứ tự gần nhất trước.
- Đọc sơ đồ phạm vi để xác định dòng nào thuộc một hoặc nhiều region.
- Dùng named region cho `@highlight`, `@replace`, `@link` và external snippet.
- Kiểm tra lỗi sai tên, thiếu marker, đóng nhầm vùng và kết quả HTML.

## 1. Nhìn region như một khoảng dòng

Một region có điểm bắt đầu và điểm kết thúc. Có thể biểu diễn phạm vi bằng hai mốc dòng:

~~~text
Dòng 1  ┌── bắt đầu region A
Dòng 2  │  Nội dung thuộc A
Dòng 3  │  Nội dung thuộc A
Dòng 4  └── kết thúc A
Dòng 5     Nội dung ngoài A
~~~

Với markup action như `@highlight`, `@replace` hoặc `@link`, thuộc tính `region` mở phạm vi của action; marker `@end` đóng phạm vi. Với external snippet, marker `@start region="A"` và `@end region="A"` đánh dấu đoạn để `{@snippet file="..." region="A"}` trích ra.

Điều quan trọng là mỗi region có thể có một khoảng dòng riêng. Khi hai khoảng giao nhau, một dòng có thể thuộc cả hai region. Khi một khoảng nằm hoàn toàn bên trong khoảng khác, ta có cấu trúc lồng nhau.

### 1.1. Region lồng nhau

Region B lồng trong region A khi B bắt đầu sau A và kết thúc trước A:

~~~text
A:  [--------------------------------]
B:       [---------------]
~~~

Ví dụ:

- A bắt đầu ở dòng 1 và kết thúc ở dòng 10.
- B bắt đầu ở dòng 3 và kết thúc ở dòng 7.
- Các dòng 3 đến 7 thuộc cả A và B.
- Các dòng 1 đến 2 và 8 đến 10 chỉ thuộc A.

### 1.2. Region chồng lấn

Hai region chồng lấn khi chúng giao nhau nhưng không region nào chứa trọn region còn lại:

~~~text
A:  [----------------------]
B:          [----------------------]
             <--- phần giao --->
~~~

Ví dụ:

- A bắt đầu ở dòng 1 và kết thúc ở dòng 6.
- B bắt đầu ở dòng 3 và kết thúc ở dòng 9.
- Các dòng 3 đến 6 thuộc cả A và B.
- Các dòng 1 đến 2 chỉ thuộc A.
- Các dòng 7 đến 9 chỉ thuộc B.

Điểm khác biệt quyết định là **thứ tự kết thúc**. Trong cấu trúc lồng nhau, vùng mở sau thường kết thúc trước. Trong cấu trúc chồng lấn, vùng mở trước có thể kết thúc trước vùng mở sau. Marker không tên khó diễn đạt trường hợp thứ hai vì nó đóng region chưa đóng gần nhất.

## 2. Vì sao nên đặt tên và đóng tường minh?

Một region không tên được mở bằng thuộc tính `region` không có giá trị và đóng bằng `@end`. `@end` không tên đóng region chưa đóng gần nhất. Cách này phù hợp với cấu trúc đơn giản hoặc lồng nhau theo thứ tự LIFO (last in, first out).

Ví dụ hai region lồng nhau không tên:

~~~java
// @highlight region substring="request" type=bold :
void send(Request request) {
    if (request == null) { // @highlight region substring="null" type=highlighted
        throw new IllegalArgumentException("request");
    } // @end
    client.send(request);
} // @end
~~~

Marker `@end` đầu tiên đóng region trong; marker thứ hai đóng region ngoài. Người đọc phải theo dõi thứ tự mở/đóng để hiểu mỗi marker thuộc về vùng nào.

Với named region, ta viết:

~~~java
// @highlight region="method" substring="send" type=bold :
void send(Request request) {
    if (request == null) { // @highlight region="validation" substring="null" type=highlighted
        throw new IllegalArgumentException("request");
    } // @end region="validation"
    client.send(request);
} // @end region="method"
~~~

Tên `method` và `validation` cho biết rõ mỗi marker đóng vùng nào. Cách viết này vẫn dễ đọc nếu sau này có thêm dòng, thêm region hoặc di chuyển marker.

**Quy tắc thực hành:** Với region lồng nhau đơn giản, marker không tên vẫn hợp lệ. Với nhiều vùng cùng tồn tại, đặc biệt khi chúng chồng lấn hoặc kết thúc không theo thứ tự mở, đặt tên riêng và dùng `@end region="name"`.

## 3. Named region trong markup action

Các markup action có thể mở một region có tên bằng thuộc tính `region`. Dạng tổng quát:

~~~java
// @highlight region="validation" substring="input" type=bold :
...
// @end region="validation"
~~~

Tương tự, `@replace` và `@link` cũng có thể dùng region:

~~~java
// @replace region="implementation" substring="calculateDetailed" replacement="calculate" :
...
// @end region="implementation"
~~~

~~~java
// @link region="apiCalls" substring="strip()" target="java.lang.String#strip()" :
...
// @end region="apiCalls"
~~~

Trong các ví dụ trên:

- Markup comment mở vùng và xác định hành động.
- Thuộc tính `region="..."` đặt tên cho vùng.
- Selector `substring` hoặc `regex` xác định phần văn bản cần thao tác trong vùng.
- `@end region="..."` đóng đúng vùng có tên.
- Marker mở và đóng không được hiển thị trong snippet.

Nếu không có selector, action áp dụng lên toàn bộ phạm vi theo quy tắc của markup tag. Khi chỉ muốn nhấn một tên hoặc liên kết một method trong vùng nhiều dòng, hãy giữ selector cụ thể.

### 3.1. Một named region bao trùm nhiều dòng

~~~java
/**
 * Nhấn tất cả lần xuất hiện của input trong quá trình kiểm tra:
 * {@snippet :
 *     // @highlight region="validation" substring="input" type=bold :
 *     if (input == null) {
 *         throw new IllegalArgumentException("input");
 *     }
 *     boolean blank = input.isBlank();
 *     if (blank) {
 *         throw new IllegalArgumentException("blank input");
 *     }
 *     // @end region="validation"
 * }
 */
public class ValidationDoc {
}
~~~

Region `validation` bắt đầu ở dòng `if` đầu tiên và kết thúc tại `@end region="validation"`. Selector `substring="input"` được tìm trên toàn bộ phạm vi. Các lần xuất hiện phù hợp trong tên biến và thông báo lỗi đều có thể được làm nổi bật vì markup xử lý văn bản, không phân tích cú pháp Java.

### 3.2. Đóng rõ ràng region action khi có vùng con

~~~java
/**
 * Ví dụ region method và validation lồng nhau:
 * {@snippet :
 *     public Response handle(Request request) { // @highlight region="method" substring="handle" type=bold
 *         if (request == null) {                 // @highlight region="validation" substring="request" type=highlighted
 *             throw new IllegalArgumentException("request");
 *         }                                      // @end region="validation"
 *         return service.execute(request);
 *     }                                          // @end region="method"
 * }
 */
public class NestedActionDoc {
}
~~~

`method` bao trùm toàn bộ method; `validation` chỉ bao trùm phần kiểm tra đầu vào. Marker kết thúc có tên giúp nhìn ra ngay vùng trong đóng trước, vùng ngoài đóng sau.

## 4. Named region khi các vùng chồng lấn

Khi hai region chồng lấn, thứ tự kết thúc có thể khác thứ tự mở. Đây là tình huống cần tên region.

Ví dụ sơ đồ:

~~~text
Dòng 1  @start A
Dòng 2  Nội dung A
Dòng 3  @start B
Dòng 4  Nội dung A + B
Dòng 5  Nội dung A + B
Dòng 6  @end A
Dòng 7  Nội dung B
Dòng 8  @end B
~~~

Khoảng A bắt đầu trước nhưng kết thúc trước B. Khoảng B bắt đầu bên trong A nhưng kết thúc sau A. Hai vùng giao nhau ở các dòng 3 đến 5.

Nếu dùng marker không tên, `@end` đóng region chưa đóng gần nhất. Khi A cần kết thúc trước B, thứ tự đóng này không thể diễn đạt đúng hai khoảng giao nhau. Đặt tên cho A và B rồi đóng từng tên riêng:

~~~java
// @highlight region="requestFlow" substring="request" type=bold :
validate(request);
// @highlight region="networkFlow" substring="client" type=highlighted :
Response response = client.send(request);
audit(response);
// @end region="requestFlow"
publish(response);
// @end region="networkFlow"
~~~

Ở ví dụ này:

- `requestFlow` mở trước.
- `networkFlow` mở sau, trong khi `requestFlow` vẫn đang mở.
- `@end region="requestFlow"` đóng vùng mở trước.
- `networkFlow` tiếp tục bao trùm dòng `publish(response)`.
- `@end region="networkFlow"` đóng vùng còn lại.

Đây là cách đặt tên và kết thúc tường minh cho các region chồng lấn. Không dựa vào vị trí gần nhất để đoán vùng cần đóng.

## 5. Ví dụ external source hoàn chỉnh với hai region chồng lấn

Một file external snippet có thể chứa nhiều vùng có tên. Ta sẽ dùng một ví dụ Java hoàn chỉnh để có thể biên dịch độc lập.

File `RegionFlows.java`:

~~~java
package demo;

import java.util.Objects;

public final class RegionFlows {
    static final class Request {
    }

    static final class Response {
    }

    static final class Client {
        Response send(Request request) {
            return new Response();
        }
    }

    private static void validate(Request request) {
        if (request == null) {
            throw new IllegalArgumentException("request");
        }
    }

    private static void audit(Response response) {
        Objects.requireNonNull(response);
    }

    private static void publish(Response response) {
        Objects.requireNonNull(response);
    }

    public void process(Request request, Client client) {
        // @start region="requestFlow"
        validate(request);
        // @start region="networkFlow"
        Response response = client.send(request);
        audit(response);
        // @end region="requestFlow"
        publish(response);
        // @end region="networkFlow"
    }
}
~~~

Hai region:

| Region | Bắt đầu | Kết thúc | Nội dung |
| --- | --- | --- | --- |
| `requestFlow` | Trước `validate(request)` | Sau `audit(response)` | Validate request, gọi client và audit response. |
| `networkFlow` | Trước `Response response = ...` | Sau `publish(response)` | Gọi client, audit và publish response. |

Phần giao nhau gồm lời gọi client và audit. `requestFlow` kết thúc trước; `networkFlow` tiếp tục đến dòng publish.

### 5.1. Tham chiếu từng region từ Javadoc

File `RegionFlowsDoc.java`:

~~~java
package demo;

/**
 * Chuẩn bị và kiểm tra request:
 * {@snippet file="RegionFlows.java" region="requestFlow"}
 *
 * Xử lý lời gọi mạng và phát hành response:
 * {@snippet file="RegionFlows.java" region="networkFlow"}
 */
public final class RegionFlowsDoc {
}
~~~

Kết quả:

- Snippet `requestFlow` chứa các dòng từ `validate(request)` đến `audit(response)`.
- Snippet `networkFlow` chứa các dòng từ lời gọi client đến `publish(response)`.
- Hai snippet có phần giao nhau vì hai region cùng bao trùm các dòng gọi client và audit.
- Marker `@start` và `@end` không xuất hiện trong HTML.

Đây là lợi ích của named region: một source có thể cung cấp nhiều góc nhìn khác nhau lên các dòng mã giao nhau mà không cần sao chép nội dung.

## 6. Region lồng nhau: dùng tên để nhìn thấy quan hệ cha/con

Với region lồng nhau, tên cũng hữu ích dù marker không tên có thể đóng theo LIFO. Hãy dùng tên thể hiện vai trò:

~~~java
// @highlight region="requestHandler" substring="handle" type=bold :
public Response handle(Request request) {
    // @highlight region="inputValidation" substring="request" type=highlighted :
    validate(request);
    // @end region="inputValidation"

    // @highlight region="serviceCall" substring="execute" type=italic :
    Response response = service.execute(request);
    // @end region="serviceCall"

    return response;
}
// @end region="requestHandler"
~~~

Có thể đọc cấu trúc:

- `requestHandler` là vùng ngoài, bao trùm method.
- `inputValidation` và `serviceCall` là hai vùng con nằm trong method.
- Mỗi vùng con được đóng ngay sau phần nội dung tương ứng.
- Vùng ngoài đóng ở cuối method.

Tên region không bắt buộc phải thể hiện quan hệ cha/con bằng dấu chấm hoặc tiền tố. Tuy nhiên, dùng quy ước nhất quán như `requestHandler`, `requestHandler.validation` và `requestHandler.serviceCall` có thể giúp source lớn dễ đọc hơn. Đây là quy ước đặt tên của dự án, không phải cú pháp đặc biệt của Javadoc.

## 7. Quy tắc ghép marker và những điều cần tránh

Khi có nhiều region cùng mở, hãy kiểm tra từng cặp theo tên:

| Marker mở | Marker đóng tương ứng |
| --- | --- |
| `@highlight region="validation"` | `@end region="validation"` |
| `@replace region="implementation"` | `@end region="implementation"` |
| `@link region="apiCalls"` | `@end region="apiCalls"` |
| `@start region="requestFlow"` | `@end region="requestFlow"` |

Các quy tắc thực hành:

1. Tên ở marker đóng phải khớp tên đã mở, bao gồm chữ hoa/chữ thường.
2. Mỗi region đang mở cần một marker kết thúc tương ứng.
3. Khi có các vùng chồng lấn, đặt tên cho từng vùng và dùng marker đóng có tên.
4. Tránh mở hai region đang hoạt động với cùng tên; tên riêng giúp việc ghép cặp rõ ràng.
5. Đừng đổi tên ở một đầu mà quên đầu còn lại.
6. Đặt marker trên dòng riêng khi dùng `@start`/`@end` cho external file để dễ nhận biết ranh giới.
7. Với markup action, đặt marker mở ở dòng bắt đầu phạm vi và selector đúng với văn bản cần xử lý.

### 7.1. Sai tên marker kết thúc

Sai:

~~~java
// @highlight region="requestFlow" substring="request" type=bold :
validate(request);
// @end region="networkFlow"
~~~

`requestFlow` được mở nhưng marker đóng lại ghi `networkFlow`. Javadoc không thể ghép marker đóng này với region `requestFlow` như người viết mong muốn.

Sửa:

~~~java
// @highlight region="requestFlow" substring="request" type=bold :
validate(request);
// @end region="requestFlow"
~~~

### 7.2. Thiếu marker kết thúc

Sai:

~~~java
// @highlight region="validation" substring="input" type=bold :
if (input == null) {
    throw new IllegalArgumentException("input");
}
System.out.println(input);
~~~

Không có `@end region="validation"`. Phạm vi không được đóng tường minh, khiến markup có thể báo lỗi hoặc không tạo phạm vi như dự định.

Sửa:

~~~java
// @highlight region="validation" substring="input" type=bold :
if (input == null) {
    throw new IllegalArgumentException("input");
}
// @end region="validation"
System.out.println(input);
~~~

### 7.3. Đóng region chồng lấn theo kiểu không tên

Nếu A mở trước B nhưng A kết thúc trước B, không dùng hai marker `@end` không tên để cố mô tả thứ tự kết thúc đó. Marker không tên đóng region chưa đóng gần nhất, phù hợp với cấu trúc lồng nhau LIFO.

Hãy dùng:

~~~java
// @highlight region="A" substring="request" type=bold :
validate(request);
// @highlight region="B" substring="client" type=highlighted :
client.send(request);
// @end region="A"
publish();
// @end region="B"
~~~

## 8. Phân biệt region của markup action và region chọn external snippet

Tên `region` xuất hiện ở hai ngữ cảnh:

| Cú pháp | Vai trò |
| --- | --- |
| `// @highlight region="validation"` ... `// @end region="validation"` | Mở phạm vi để action làm nổi bật văn bản nhiều dòng. |
| `// @start region="validation"` ... `// @end region="validation"` | Đánh dấu đoạn trong external file để có thể được tham chiếu. |
| `{@snippet file="Validation.java" region="validation"}` | Chọn vùng đã đánh dấu để đưa vào khối mã HTML. |

Hai cách đầu đều dùng tên và marker đóng, nhưng mục đích khác nhau. `@highlight region` mở phạm vi của action highlight; `@start region` đánh dấu một đoạn external để tag `{@snippet}` chọn.

Ví dụ external file:

~~~java
package demo;

public final class Validation {
    public static void check(String input) {
        // @start region="validation"
        if (input == null) {
            throw new IllegalArgumentException("input");
        }
        if (input.isBlank()) {
            throw new IllegalArgumentException("blank");
        }
        // @end region="validation"
    }
}
~~~

Javadoc:

~~~java
/**
 * Chỉ trích phần kiểm tra:
 * {@snippet file="Validation.java" region="validation"}
 */
public final class ValidationDoc {
}
~~~

Nếu muốn làm nổi bật thêm văn bản trong phần được trích, hãy cấu hình markup action phù hợp. Đừng nhầm việc chọn vùng external với việc mở vùng cho một action.

## 9. Quy trình thiết kế region cho source lớn

Với file có nhiều vùng, hãy lập bản đồ phạm vi trước khi thêm marker. Quy trình sau giúp tránh sai tên và đóng nhầm:

1. **Xác định mục tiêu trình bày.** Quyết định cần trích cả quy trình, một bước con hay hai đoạn mã giao nhau.
2. **Đánh dấu dòng bắt đầu và kết thúc.** Ghi lại vị trí từng region trước khi viết comment.
3. **Vẽ khoảng dòng.** Xác định quan hệ là lồng nhau hay chồng lấn.
4. **Đặt tên riêng.** Chọn tên theo vai trò, ví dụ `requestFlow`, `networkFlow`, `validation`.
5. **Viết marker mở.** Dùng `@start region="name"` cho external snippet hoặc markup action có `region="name"`.
6. **Viết marker đóng tường minh.** Dùng `@end region="name"` đúng với từng region.
7. **Đối chiếu cặp marker.** Mỗi tên mở phải có một điểm kết thúc đúng tên.
8. **Sinh Javadoc.** Kiểm tra warning/error về region và markup.
9. **Đọc HTML.** Xác nhận từng snippet có đúng dòng đầu/cuối và phần giao nhau như mong muốn.
10. **Biên dịch external Java source nếu cần.** Marker là comment, nên file source hoàn chỉnh có thể được kiểm tra độc lập bằng `javac`.

Bảng theo dõi có thể dùng khi review:

| Tên region | Dòng bắt đầu | Dòng kết thúc | Quan hệ | Đã kiểm tra |
| --- | --- | --- | --- | --- |
| `requestHandler` | Khai báo method | Cuối method | Ngoài | Có/Không |
| `validation` | Bắt đầu kiểm tra | Sau điều kiện cuối | Lồng trong requestHandler | Có/Không |
| `networkFlow` | Trước client.send | Sau publish | Chồng lấn requestFlow | Có/Không |

Bảng này không phải cú pháp Javadoc. Đây là cách quản lý phạm vi khi source có nhiều marker và nhiều người cùng bảo trì.

## 10. Kiểm chứng bằng `javadoc` và `javac`

Đối với external snippet, kiểm tra hai lớp riêng biệt:

- `javac` xác nhận file Java external có cú pháp và kiểu hợp lệ.
- `javadoc` xác nhận marker region, thuộc tính `region` và nội dung HTML được xử lý đúng.

Giả sử cấu trúc:

~~~text
src/
└── demo/
    ├── RegionFlowsDoc.java
    └── snippet-files/
        └── RegionFlows.java
~~~

Biên dịch file external:

~~~bash
javac -d out src/demo/snippet-files/RegionFlows.java
~~~

Sinh tài liệu:

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Mở `docs/demo/RegionFlowsDoc.html` và kiểm tra:

1. Snippet `requestFlow` bắt đầu tại `validate(request)`.
2. Snippet `requestFlow` kết thúc sau `audit(response)`.
3. Snippet `networkFlow` bắt đầu tại `Response response = client.send(...)`.
4. Snippet `networkFlow` kết thúc sau `publish(response)`.
5. Các dòng `client.send` và `audit` xuất hiện trong cả hai snippet vì hai vùng chồng lấn.
6. Marker `@start` và `@end` không xuất hiện trong nội dung mã được hiển thị.

Nếu dùng markup action trong inline snippet, mở HTML của class chứa documentation comment và kiểm tra từng phần được highlight/link/replace. Đừng chỉ nhìn tên marker trong source; HTML là kết quả cuối cùng để xác nhận phạm vi.

### 10.1. Khi Javadoc báo lỗi

Kiểm tra theo thứ tự:

- Tên region có giống nhau ở điểm mở và điểm đóng không?
- Có marker kết thúc bị thiếu không?
- Có marker đóng nhầm tên region khác không?
- Có hai region cùng tên đang mở khiến việc ghép cặp khó xác định không?
- Có dùng marker external `@start`/`@end` lẫn với marker của markup action mà không chủ ý không?
- Thuộc tính `region` của `{@snippet}` có khớp tên vùng trong file external không?
- File external có nằm trong `snippet-files` hoặc đường dẫn `--snippet-path` được cấu hình không?

Sau khi sửa, sinh lại Javadoc và xem HTML mới. Không dùng HTML cũ để kết luận marker đã được sửa đúng.

## 11. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng region không tên cho các khoảng chồng lấn. | `@end` không tên đóng region chưa đóng gần nhất, không xác định được cặp kết thúc theo ý muốn. | Đặt tên riêng và dùng `@end region="name"`. |
| Mở A, mở B, đóng A bằng `@end`. | Marker không tên sẽ đóng B vì B được mở gần nhất. | Dùng `@end region="A"` để đóng A tường minh. |
| Tên mở và đóng khác nhau. | Javadoc không ghép được marker theo tên. | Đối chiếu chính xác tên ở hai đầu. |
| Quên đóng region ngoài sau khi đã đóng region trong. | Vùng ngoài vẫn đang mở. | Thêm marker đóng cho từng region. |
| Tái sử dụng cùng tên cho các vùng đang mở đồng thời. | Khó phân biệt cặp marker và có thể làm cấu trúc không hợp lệ. | Dùng tên riêng cho từng region đang hoạt động. |
| Nghĩ region có tên tự tạo một snippet riêng. | Tên chỉ định danh phạm vi; phải có `{@snippet region=...}` để chọn external region hoặc markup action để áp dụng định dạng. | Phân biệt marker, selector và tag tham chiếu. |
| Nghĩ hai region chồng lấn không thể cùng được trích. | Mỗi region có tên có thể được chọn riêng; phần giao có thể xuất hiện trong cả hai snippet. | Tham chiếu từng tên region bằng các `{@snippet}` riêng. |
| Chỉ kiểm tra file source. | Marker nhìn có vẻ đúng nhưng HTML có thể trích sai phạm vi. | Sinh Javadoc và kiểm tra nội dung, điểm bắt đầu/kết thúc trong HTML. |
| Chỉ kiểm tra HTML mà bỏ qua source. | Snippet hiển thị có thể đúng nhưng external Java file có thể không biên dịch. | Chạy `javac` khi cần xác nhận source hoàn chỉnh. |

## 12. Bài tập tự đánh giá

### Bài 1 — Phân biệt lồng nhau và chồng lấn

A mở ở dòng 1, B mở ở dòng 3, A đóng ở dòng 6 và B đóng ở dòng 9. Đây là cấu trúc nào?

**Đáp án:** Hai region chồng lấn. A bắt đầu trước nhưng kết thúc trước B; B bắt đầu trong A và tiếp tục sau khi A kết thúc.

### Bài 2 — Vì sao marker không tên không phù hợp?

~~~java
// @highlight region substring="request" type=bold :
validate(request);
// @highlight region substring="client" type=highlighted :
client.send(request);
// @end
publish();
// @end
~~~

Nếu muốn vùng đầu kết thúc ngay sau `client.send` và vùng thứ hai tiếp tục đến sau `publish`, cách viết trên có đáp ứng không?

**Đáp án:** Không. `@end` đầu tiên đóng region mở gần nhất, tức region thứ hai. Để đóng vùng đầu trước vùng thứ hai, cần đặt tên:

~~~java
// @highlight region="A" substring="request" type=bold :
validate(request);
// @highlight region="B" substring="client" type=highlighted :
client.send(request);
// @end region="A"
publish();
// @end region="B"
~~~

### Bài 3 — Sửa marker kết thúc sai tên

~~~java
// @replace region="implementation" substring="internalCall" replacement="call" :
internalCall();
// @end region="usage"
~~~

**Đáp án:** Đổi marker cuối thành `@end region="implementation"`.

### Bài 4 — Chọn vùng external

File external có hai region `setup` và `send`, hai vùng chồng lấn. Muốn hiển thị từng vùng ở hai đoạn tài liệu, cần viết bao nhiêu tag snippet?

**Đáp án:** Hai tag `{@snippet}`, cùng tham chiếu một file nhưng lần lượt dùng `region="setup"` và `region="send"`.

### Bài 5 — Region action và external region khác nhau thế nào?

`@highlight region="validation"` và `@start region="validation"` có cùng chức năng không?

**Đáp án:** Không. `@highlight region` mở phạm vi cho hành động làm nổi bật. `@start region` đánh dấu một vùng external để tag `{@snippet}` có thể chọn.

### Bài 6 — Có nên đặt tên cho mọi region?

Một snippet chỉ có một vùng nhỏ, mở một lần và đóng ngay sau đó. Có bắt buộc đặt tên không?

**Đáp án:** Không. Region không tên vẫn phù hợp với phạm vi đơn giản và đóng theo thứ tự LIFO. Tên đặc biệt hữu ích khi có nhiều vùng, lồng nhau sâu hoặc chồng lấn.

## Tổng kết

- Region lồng nhau có một vùng nằm trọn bên trong vùng khác; region chồng lấn giao nhau nhưng không chứa trọn nhau.
- Region không tên đóng bằng `@end` và tuân theo quy tắc đóng vùng chưa đóng gần nhất (LIFO).
- Region có tên mở bằng `region="name"` và đóng tường minh bằng `@end region="name"`.
- Khi các region chồng lấn và kết thúc khác thứ tự mở, hãy đặt tên riêng cho từng vùng và đóng theo tên.
- Named region giúp người đọc hiểu điểm bắt đầu/kết thúc, giảm lỗi ghép marker khi source được sửa.
- `@highlight`, `@replace` và `@link` có thể dùng named region làm phạm vi action; `@start`/`@end` có thể đánh dấu named region trong external snippet.
- `{@snippet file="..." region="name"}` chọn một named region để hiển thị; các vùng chồng lấn có thể được trích riêng và có phần nội dung giao nhau.
- Hãy kiểm tra marker, chạy `javadoc` và đọc HTML; với external Java source, chạy thêm `javac` để xác nhận file nguồn hợp lệ.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Guide: Snippets, JDK 26, mục Regions](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): region có tên, không tên, nested regions và overlapping regions.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 26, mục Snippets và Regions](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html#snippet): cú pháp markup region, marker bắt đầu/kết thúc và cách phân giải phạm vi.
3. [Oracle — The javadoc Command, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): sinh tài liệu, external snippet và tùy chọn đường dẫn tìm snippet.
4. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): thiết kế snippet và markup comment được đưa vào Java 18.
