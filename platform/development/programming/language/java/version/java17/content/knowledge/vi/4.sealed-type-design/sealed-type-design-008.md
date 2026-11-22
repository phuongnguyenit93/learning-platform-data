# Thay đổi danh sách kiểu con của `sealed` và ảnh hưởng tới mã sử dụng trong Java 17

**Chủ đề:** Java 17 → Thiết kế với sealed  
**Trọng tâm:** Hiểu điều gì xảy ra khi thêm, bớt hoặc thay đổi kiểu con trong một hệ phân cấp `sealed`, từ lỗi biên dịch đến thay đổi hành vi ở chương trình đang chạy.

Trong Java 17, `sealed class` và `sealed interface` là tính năng ngôn ngữ **chính thức**. Chúng cho phép kiểu cha quy định những kiểu nào được phép **trực tiếp** `extends` hoặc `implements` nó. Danh sách đó thường thể hiện những trường hợp mà ứng dụng biết cách xử lý. Vì vậy, khi danh sách thay đổi, ta không chỉ sửa một dòng khai báo: ta đang thay đổi hợp đồng của mô hình dữ liệu với mã sử dụng nó.

Bài này chỉ sử dụng các tính năng ổn định của **Java 17**, chẳng hạn `sealed`, `record` và pattern matching của `instanceof`. Không dùng pattern matching cho `switch`, vì tính năng này vẫn ở trạng thái *preview* trong chính Java 17.

## 1. Danh sách `permits` là một phần của hợp đồng kiểu

Xét mô hình kết quả xử lý:

~~~java
public sealed interface OperationResult
        permits OperationResult.Success, OperationResult.Failure {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}
}
~~~

Khai báo trên có ý nghĩa:

- `OperationResult` chỉ cho phép `Success` và `Failure` **trực tiếp** triển khai nó.
- Hai kiểu con là `record`, nên tự có tính chất `final`: không thể tạo lớp kế thừa từ một record.
- Mã sử dụng biết rằng mô hình hiện được thiết kế với hai trường hợp trực tiếp.
- `permits` **không** tự bảo đảm mọi nhánh `if` trong mã sử dụng đã xử lý đúng; đây vẫn là trách nhiệm của chương trình.

Ta có thể biểu diễn cấu trúc ban đầu:

~~~text
OperationResult (sealed interface)
├── Success (record, final)
└── Failure (record, final)
~~~

Khi bổ sung trường hợp `Pending`:

~~~java
public sealed interface OperationResult
        permits OperationResult.Success,
                OperationResult.Failure,
                OperationResult.Pending {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}

    record Pending(String requestId) implements OperationResult {}
}
~~~

thì tập trường hợp được phép đã mở rộng:

~~~text
OperationResult (sealed interface)
├── Success (record, final)
├── Failure (record, final)
└── Pending (record, final)   ← trường hợp mới
~~~

Sự thay đổi hợp lệ ở phía thư viện vẫn có thể làm một đoạn mã sử dụng cũ xử lý sai hoặc phát sinh ngoại lệ khi nhận `Pending`.

> **Phân biệt quan trọng:** `permits` giới hạn các kiểu con **trực tiếp**. Nếu một kiểu con là `non-sealed`, các kiểu con **gián tiếp** có thể tiếp tục xuất hiện mà không cần thêm tên vào danh sách `permits` ở cấp gốc.

## 2. Những kiểu thay đổi cần phân biệt

| Thay đổi | Hệ phân cấp sau khi sửa | Tác động đáng chú ý tới mã sử dụng |
| --- | --- | --- |
| **Thêm kiểu con trực tiếp** vào `permits` | Xuất hiện một trường hợp hợp lệ mới. | Mã cũ có thể chưa biết cách hiển thị, lưu trữ hoặc xử lý trường hợp này. |
| **Bỏ kiểu con** khỏi `permits` | Kiểu đó không còn được phép trực tiếp kế thừa/triển khai. | Nếu mã nguồn kiểu con vẫn giữ quan hệ cũ thì không biên dịch; binary cũ cũng có nguy cơ lỗi liên kết khi nạp. |
| **Đổi tên hoặc chuyển kiểu con sang package/module khác** | Tên nhị phân, khả năng truy cập hoặc vị trí trong hệ phân cấp có thể đổi. | Mã import, khởi tạo, so khớp kiểu và phụ thuộc đã biên dịch có thể bị ảnh hưởng. |
| Đổi kiểu con từ **`final` sang `non-sealed`** (nếu đó là lớp con của kiểu sealed và khai báo hợp lệ) | Nhánh đó có thể được kế thừa tiếp. | Mã trước đây giả định nhánh “đóng” phải xem xét trường hợp các kiểu con gián tiếp mới. |
| Đổi một kiểu con từ **`non-sealed` sang `sealed`** | Nhánh mở trở thành nhánh hạn chế kiểu con trực tiếp. | Các lớp con không nằm trong danh sách được phép có thể không còn hợp lệ. |
| Thay hình dạng dữ liệu hoặc hành vi của một kiểu con | Danh sách `permits` có thể vẫn giữ nguyên. | Constructor, accessor, quy tắc xác thực và kết quả nghiệp vụ của mã sử dụng có thể thay đổi. |

Không có một kết luận “tương thích” chung cho mọi thay đổi. Cần đánh giá ít nhất **ba tầng**: mã nguồn có biên dịch lại được không, mã nhị phân đã biên dịch có tải/chạy được không, và hành vi nghiệp vụ còn đúng không.

## 3. Ví dụ từng bước: thêm một kiểu con mới

Ta xây dựng API nhỏ có thể biên dịch với Java 17, rồi quan sát tác động của việc thêm `Pending`.

### 3.1. Phiên bản 1 — chỉ có `Success` và `Failure`

**Tệp `OperationResult.java`:**

~~~java
public sealed interface OperationResult
        permits OperationResult.Success, OperationResult.Failure {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}
}
~~~

**Tệp `ResultPrinter.java`:**

~~~java
public class ResultPrinter {
    static String format(OperationResult result) {
        if (result instanceof OperationResult.Success success) {
            return "Thành công: " + success.value();
        }
        if (result instanceof OperationResult.Failure failure) {
            return "Thất bại: " + failure.reason();
        }

        throw new IllegalArgumentException(
            "Kiểu kết quả chưa được hỗ trợ: " + result.getClass().getName()
        );
    }

    public static void main(String[] args) {
        OperationResult result = new OperationResult.Success("Đã lưu");
        System.out.println(format(result));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~shell
javac --release 17 OperationResult.java ResultPrinter.java
java ResultPrinter
~~~

Kết quả:

~~~text
Thành công: Đã lưu
~~~

Trong phiên bản 1, mã `format` có hai nhánh `instanceof` tương ứng với hai kiểu con được cho phép. Nhánh ném ngoại lệ thể hiện chính sách **fail fast** nếu xuất hiện loại mà hàm không hỗ trợ.

### 3.2. Phiên bản 2 — bổ sung `Pending`

Thay nội dung `OperationResult.java` bằng:

~~~java
public sealed interface OperationResult
        permits OperationResult.Success,
                OperationResult.Failure,
                OperationResult.Pending {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}

    record Pending(String requestId) implements OperationResult {}
}
~~~

Nếu một thành phần khác tạo `new OperationResult.Pending("REQ-42")` và đưa giá trị đó cho phương thức `ResultPrinter.format` ở phiên bản 1, hai điều kiện `instanceof` cũ đều sai. Mã sẽ đi vào nhánh ném `IllegalArgumentException`.

Lưu ý sự khác biệt:

- **API của phiên bản 2 có thể được biên dịch hợp lệ**: `Pending` đã được khai báo trong `permits` và là một record `final` ngầm định.
- **Mã sử dụng phiên bản 1 vẫn có thể biên dịch lại**: chuỗi `if`/`instanceof` trong Java 17 không có cơ chế kiểm tra tính bao phủ toàn bộ các nhánh của một kiểu sealed.
- **Hành vi có thể không còn phù hợp**: hệ thống bắt đầu nhận một kết quả hợp lệ mới nhưng cách xử lý cũ không hỗ trợ.

Đây là ví dụ điển hình về thay đổi **tương thích ở mức biên dịch** nhưng cần cập nhật **ở mức hành vi**.

### 3.3. Cập nhật mã sử dụng để hỗ trợ kiểu mới

Có thể sửa phương thức `format`:

~~~java
static String format(OperationResult result) {
    if (result instanceof OperationResult.Success success) {
        return "Thành công: " + success.value();
    }
    if (result instanceof OperationResult.Failure failure) {
        return "Thất bại: " + failure.reason();
    }
    if (result instanceof OperationResult.Pending pending) {
        return "Đang xử lý, mã yêu cầu: " + pending.requestId();
    }

    throw new IllegalArgumentException(
        "Kiểu kết quả chưa được hỗ trợ: " + result.getClass().getName()
    );
}
~~~

Với `new OperationResult.Pending("REQ-42")`, kết quả sẽ là:

~~~text
Đang xử lý, mã yêu cầu: REQ-42
~~~

Đoạn mã này dùng **pattern matching for `instanceof`**, tính năng chính thức có sẵn trong Java 17. Không cần cú pháp `case Pending p -> ...` trong `switch` vì pattern matching trong `switch` vẫn là preview ở Java 17.

### 3.4. Nhánh dự phòng nên làm gì?

Không tồn tại một cách xử lý dự phòng phù hợp cho mọi ứng dụng. Một số lựa chọn:

| Trường hợp sử dụng | Chính sách khi gặp subtype mới | Lý do |
| --- | --- | --- |
| Chỉ hiển thị thông tin cho người dùng | Có thể dùng nhãn trung tính, kèm ghi nhận sự kiện để cập nhật giao diện. | Tránh làm sập luồng hiển thị vì kiểu mới chưa được trình bày chi tiết. |
| Xử lý giao dịch, quyết định tài chính hoặc phân quyền | Từ chối an toàn hoặc dừng thao tác rõ ràng; không tự gán kiểu mới thành thành công. | Phân loại sai có thể làm thay đổi trạng thái nghiệp vụ nghiêm trọng. |
| Đồng bộ dữ liệu giữa nhiều phiên bản dịch vụ | Thỏa thuận trước chính sách tương thích cho giá trị mới; có thể áp dụng phiên bản giao thức. | Bên nhận cũ cần biết phải bỏ qua, lưu trữ, chặn hay báo lỗi. |
| API yêu cầu chỉ những trường hợp đã định nghĩa được chấp nhận | Ném ngoại lệ với thông tin kiểu cụ thể. | Giúp phát hiện việc triển khai chưa bắt kịp hợp đồng. |

Ví dụ mẫu tránh cách viết mặc định như:

~~~java
// Không nên: tự xem mọi kiểu không hiểu là thành công.
return "Thành công";
~~~

Điểm cần quyết định là **ngữ nghĩa của kiểu mới**, không chỉ việc ngăn ứng dụng ném ngoại lệ.

## 4. Thêm kiểu con: mã nguồn, binary và hành vi khác nhau ra sao?

Khi thay một thư viện chứa sealed hierarchy phiên bản 1 bằng phiên bản 2, cần phân biệt:

**Tương thích mã nguồn (source compatibility)** nghĩa là mã sử dụng có thể được biên dịch lại với API mới. Với các nhánh `if`/`instanceof` như trên, việc **chỉ bổ sung** một kiểu con thường không làm các nhánh hiện có lỗi biên dịch. Tuy nhiên các quy tắc khác như constructor, phương thức, visibility và những phần API thay đổi cùng lúc vẫn phải được xem xét.

**Tương thích nhị phân (binary compatibility)** nghĩa là các class file đã biên dịch từ trước có thể liên kết và làm việc với phiên bản thư viện mới theo các quy tắc của JVM. Việc **thêm** một kiểu con được phép nói chung không buộc các binary consumer cũ phải biên dịch lại, miễn là những lớp, phương thức, tên nhị phân và cấu trúc API đang dùng vẫn được giữ. Đây không phải cam kết mọi kết quả lúc chạy sẽ như trước.

**Tương thích hành vi (behavioral compatibility)** nghĩa là chương trình vẫn xử lý đúng đầu vào và kết quả mới. Một binary cũ có thể nạp thành công rồi ném ngoại lệ ở nhánh “loại chưa hỗ trợ”, ghi nhầm dữ liệu, bỏ qua sự kiện, hoặc trả về nội dung thiếu chính xác.

Ví dụ trực quan:

~~~text
Thư viện v1
    OperationResult -> Success | Failure
           │
           ▼
Mã client v1: xử lý Success, Failure

Thư viện v2
    OperationResult -> Success | Failure | Pending
           │
           ▼
Mã client v1: có thể chạy, nhưng chưa biết xử lý Pending
           │
           ▼
Mã client v2: xử lý Pending theo nghiệp vụ mới
~~~

**Thêm vào `permits` không tự động cập nhật client.** Với thư viện công khai, phát hành phiên bản mới và cung cấp ghi chú thay đổi là một phần của việc duy trì hợp đồng API.

## 5. Xóa kiểu con: tác động có thể nghiêm trọng hơn

Giả sử ban đầu:

~~~java
sealed interface JobState permits Running, Paused, Stopped {
}

record Running() implements JobState {}

record Paused() implements JobState {}

record Stopped() implements JobState {}
~~~

Sau một thời gian, ứng dụng loại bỏ trạng thái `Paused` và sửa sealed interface thành:

~~~java
sealed interface JobState permits Running, Stopped {
}
~~~

Có hai trường hợp khác nhau.

### 5.1. Vẫn giữ source của `Paused`

Nếu `Paused` vẫn viết `implements JobState` trong mã nguồn, trình biên dịch Java 17 sẽ không chấp nhận vì `Paused` không còn nằm trong danh sách kiểu con trực tiếp được phép.

Để xây dựng lại từ source, nhóm phát triển phải thực sự di chuyển/xóa/mô hình hóa lại `Paused`, đồng thời sửa những nơi tạo và dùng đối tượng đó.

### 5.2. Vẫn có class file `Paused` từ phiên bản cũ

Khi một binary `Paused` đã biên dịch trước đó vẫn triển khai `JobState` nhưng bản `JobState` mới không cho phép kiểu này, JVM có thể báo **`IncompatibleClassChangeError` khi nạp/liên kết kiểu con**. Đây là rủi ro **tương thích nhị phân** của việc thu hẹp danh sách con được phép. Nếu lớp `Paused` đã bị xóa khỏi dependency mà client cũ vẫn tham chiếu tới nó, các lỗi phân giải lớp như `NoClassDefFoundError` cũng có thể xuất hiện.

Không nên giả định rằng “mã đã biên dịch rồi nên không bị ảnh hưởng bởi `permits`”. Sealed hierarchy được biểu diễn trong metadata của class file và được JVM kiểm tra.

### 5.3. Quy trình loại bỏ ít gây gián đoạn

Một quy trình thực tế có thể gồm:

1. **Xác định mọi vị trí phụ thuộc:** constructor, `instanceof`, API trả về, dữ liệu lưu trữ và message/event liên quan `Paused`.
2. **Ngừng sinh ra trạng thái cũ** theo cách có chủ đích, đồng thời tiếp tục xử lý các giá trị cũ nếu chúng còn tồn tại.
3. **Chuyển đổi dữ liệu và hợp đồng giao tiếp** sang trạng thái thay thế. Không tự gán trạng thái cũ sang trạng thái khác nếu ngữ nghĩa chưa được xác định.
4. **Cập nhật tất cả thành phần sử dụng**, rồi mới phát hành thay đổi loại bỏ trong hệ phân cấp.
5. **Xây dựng và triển khai nhất quán** thư viện cùng mã client, tránh trộn binary của hai phiên bản không tương thích.

Với API dùng chung cho nhiều nhóm, việc loại bỏ subtype có thể đòi hỏi phát hành thay đổi lớn (breaking change), chứ không chỉ bổ sung một release nhỏ.

## 6. Thay đổi `final`, `sealed` và `non-sealed` ở các nhánh

Danh sách trực tiếp trong `permits` không phải là toàn bộ cây kế thừa. Hình dạng các nhánh cũng quan trọng.

### 6.1. Một nhánh `final` là nhánh đóng

~~~java
sealed interface Notification
        permits Email, Internal {
}

record Email(String address) implements Notification {}

final class Internal implements Notification {}
~~~

`Email` là record và `Internal` là final class, nên không thể tạo subtype của hai lớp này. Nếu API chỉ gồm các nhánh đóng như vậy, tập loại cụ thể có thể được nhìn nhận khá rõ từ phân cấp.

### 6.2. Một nhánh `non-sealed` cho phép mở rộng gián tiếp

~~~java
sealed interface Notification
        permits Email, External {
}

record Email(String address) implements Notification {}

non-sealed interface External extends Notification {
    String target();
}

final class Webhook implements External {
    @Override
    public String target() {
        return "https://example.com/hook";
    }
}
~~~

Ở đây `Notification` vẫn chỉ cho phép hai kiểu con **trực tiếp** là `Email` và `External`. Tuy nhiên `Webhook` là lớp triển khai gián tiếp hợp lệ thông qua `External`; sau này còn có thể xuất hiện các kiểu khác `implements External`.

Điều đó ảnh hưởng đến mã sử dụng:

~~~java
static String describe(Notification notification) {
    if (notification instanceof Email email) {
        return "Email: " + email.address();
    }
    if (notification instanceof External external) {
        return "Hệ thống ngoài: " + external.target();
    }
    throw new IllegalArgumentException("Loại chưa hỗ trợ");
}
~~~

Nhánh `External` xử lý được cả `Webhook` và những triển khai khác của `External`. Nhưng nếu từng triển khai cần hành vi khác nhau, chỉ kiểm tra interface cha sẽ không đủ. Hãy xem xét liệu nên dùng một hợp đồng chung, thêm phương thức đa hình, hay đưa từng trường hợp quan trọng vào mô hình kiểu.

**Cảnh báo thiết kế:** không thể suy luận rằng một kiểu sealed chỉ có đúng hai kiểu đối tượng cụ thể vì `permits` liệt kê hai tên. Phải kiểm tra liệu nhánh nào là `non-sealed`.

### 6.3. Giới hạn lại một nhánh bằng `sealed`

Giả sử ban đầu `External` là `non-sealed` và thư viện bên ngoài tự triển khai nó. Nếu đổi `External` thành `sealed interface External permits Webhook`, các triển khai cũ khác sẽ không còn được phép trực tiếp kế thừa `External`. Đây có thể là thay đổi phá vỡ mã nguồn hoặc binary của các phần mở rộng đang tồn tại.

Trước khi thu hẹp nhánh, phải xác định ai sở hữu và triển khai các subtype, kể cả subtype nằm trong module khác. Với named module, các subtype trực tiếp được cho phép phải nằm trong cùng named module với kiểu sealed; với unnamed module, chúng phải ở cùng package.

## 7. Đổi tên, di chuyển và sửa cấu trúc subtype

Không phải mọi thay đổi nguy hiểm đều thể hiện bằng việc thêm hoặc xóa một tên trong `permits`.

**Đổi tên `Failure` thành `Rejected`:** các client có `new Failure(...)`, `instanceof Failure`, import `Failure`, hoặc gọi accessor riêng của `Failure` phải cập nhật. Nếu loại bỏ class file cũ, binary đang tham chiếu tên cũ sẽ gặp lỗi liên kết/phân giải lớp. Chỉ đổi tên trong tài liệu mà không có chính sách chuyển đổi là chưa đủ.

**Chuyển subtype sang package/module khác:** cần xem lại `permits`, import, visibility, tên nhị phân và quy tắc same-package/same-module của Java 17. Di chuyển subtype ra ngoài phạm vi được phép không thể khắc phục bằng cách ghi tên mới trong `permits`.

**Đổi record thành class thường:** dù kiểu mới vẫn hợp lệ trong `permits`, mã sử dụng có thể phụ thuộc vào canonical constructor, accessor của record, `equals`, `hashCode`, `toString` hoặc khả năng khởi tạo bằng cú pháp record. Đây là thay đổi về hợp đồng dữ liệu cần đánh giá riêng.

**Thay đổi constructor, field, method hoặc cấu trúc generic:** ngay cả khi danh sách subtype không đổi, source/binary/behavioral compatibility vẫn có thể bị ảnh hưởng. Sealed không thay thế nguyên tắc quản lý phiên bản API thông thường.

## 8. Cách viết mã sử dụng phù hợp với Java 17

### 8.1. Dùng `instanceof` pattern matching một cách rõ ràng

Mã Java 17 có thể xử lý từng nhánh bằng:

~~~java
if (result instanceof OperationResult.Success success) {
    // Sử dụng success.value()
} else if (result instanceof OperationResult.Failure failure) {
    // Sử dụng failure.reason()
} else {
    // Quyết định chính sách khi API phát sinh subtype mới.
}
~~~

Đây là cú pháp Java 17 ổn định. Nó không yêu cầu bật preview và cũng **không tự sinh cảnh báo** khi một sealed interface nhận thêm subtype mới.

### 8.2. Ưu tiên hành vi đa hình khi phù hợp

Trong một số trường hợp, thay vì đặt chuỗi `instanceof` trong nhiều client, có thể khai báo hành vi chung:

~~~java
sealed interface DisplayResult permits DisplayResult.Ok, DisplayResult.Error {
    String displayText();

    record Ok(String value) implements DisplayResult {
        @Override
        public String displayText() {
            return "Thành công: " + value;
        }
    }

    record Error(String reason) implements DisplayResult {
        @Override
        public String displayText() {
            return "Lỗi: " + reason;
        }
    }
}
~~~

Client chỉ cần:

~~~java
String text = result.displayText();
~~~

Nếu sau này thư viện thêm một subtype trực tiếp mới, subtype đó cũng phải hiện thực hợp đồng `displayText()` (trừ khi có cách hiện thực hợp lệ được thừa kế). Cách này tập trung logic hiển thị gần dữ liệu và có thể giảm số nơi client cần sửa.

Tuy nhiên **không phải mọi quyết định đều nên đặt vào subtype**: lưu trữ, phân quyền, giao diện và quy tắc nghiệp vụ của từng client có thể khác nhau. Dùng đa hình khi đó thực sự là hành vi chung và thuộc trách nhiệm của mô hình.

### 8.3. Tránh dựa vào switch pattern preview của Java 17

Trong Java 17, các ví dụ kiểu:

~~~java
// Không dùng làm ví dụ Java 17 ổn định:
// return switch (result) {
//     case OperationResult.Success s -> s.value();
//     case OperationResult.Failure f -> f.reason();
// };
~~~

thuộc hướng pattern matching trong `switch` đang được thử nghiệm ở Java 17. Những phân tích về tính bao phủ toàn bộ các trường hợp trong `switch` pattern ở các phiên bản mới hơn không nên bị áp đặt như một bảo đảm của ngôn ngữ Java 17 thông thường.

Khi khóa học nhắm Java 17, hãy dùng `instanceof`, phương thức đa hình hoặc thiết kế API rõ hợp đồng như các ví dụ ở trên.

## 9. Quan sát danh sách permitted subtype bằng reflection

Java 17 có API reflection chính thức `Class.isSealed()` và `Class.getPermittedSubclasses()`. Có thể sử dụng chúng khi cần công cụ chẩn đoán hoặc kiểm tra cấu trúc hệ phân cấp đang thực sự được nạp.

Với tệp `OperationResult.java` phiên bản 2 ở trên, tạo **`InspectPermits.java`**:

~~~java
public class InspectPermits {
    public static void main(String[] args) {
        Class<OperationResult> type = OperationResult.class;

        System.out.println("Sealed: " + type.isSealed());

        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted != null) {
            for (Class<?> subtype : permitted) {
                System.out.println(subtype.getName());
            }
        }
    }
}
~~~

Biên dịch với:

~~~shell
javac --release 17 OperationResult.java InspectPermits.java
java InspectPermits
~~~

Với phiên bản 2, kết quả dự kiến là `Sealed: true` và các tên lớp lồng nhau tương ứng với `Success`, `Failure`, `Pending` (chẳng hạn `OperationResult$Success`). Không nên phụ thuộc vào thứ tự in ra để thiết kế logic nghiệp vụ.

`getPermittedSubclasses()` trả về những kiểu con **trực tiếp** được cho phép, không phải truy vấn tự động toàn bộ hậu duệ ở nhiều cấp. Với kiểu không `sealed`, API này trả về `null`. Reflection hữu ích khi cần quan sát runtime, nhưng **không thay thế** chính sách versioning và việc sửa mã xử lý subtype mới.

## 10. Tác động tới dữ liệu đã lưu và giao tiếp giữa dịch vụ

`sealed` là quy tắc của hệ kiểu Java; nó không mặc nhiên quản lý định dạng JSON, dữ liệu cơ sở dữ liệu, event trên message broker hay khả năng tương thích giữa các phiên bản dịch vụ.

Ví dụ một ứng dụng tuần tự hóa kết quả thành:

~~~json
{
  "type": "success",
  "value": "Đã lưu"
}
~~~

Nếu sau khi mở rộng hệ phân cấp, một ứng dụng mới gửi:

~~~json
{
  "type": "pending",
  "requestId": "REQ-42"
}
~~~

thì ứng dụng cũ chỉ biết `success` và `failure` có thể không giải mã được thông điệp mới. Việc sealed interface mới có `Pending` **không khiến bộ giải mã cũ tự hiểu khóa `type=pending`**.

Khi quản lý dữ liệu qua nhiều phiên bản, nên làm rõ:

1. **Định dạng và mã phân biệt kiểu:** ví dụ `success`, `failure`, `pending`, được quy định trong hợp đồng dữ liệu và không bị thay đổi tùy tiện theo tên lớp.
2. **Khả năng đọc dữ liệu cũ:** sau khi bỏ `Failure` hoặc đổi tên, ứng dụng mới sẽ xử lý bản ghi cũ ra sao?
3. **Khả năng phía nhận cũ gặp dữ liệu mới:** sẽ từ chối, lưu tạm, bỏ qua có ghi nhận, hay dùng phiên bản giao thức khác?
4. **Thời điểm triển khai:** nâng cấp người đọc và người ghi theo thứ tự nào để không sinh ra trường hợp chưa được hỗ trợ?
5. **Giới hạn bảo mật và hợp lệ dữ liệu:** chỉ chấp nhận subtype/giá trị được phép theo bộ phân tích và quy tắc nghiệp vụ, không tự tin tưởng dữ liệu bên ngoài vì lớp Java là sealed.

Trong hệ thống phân tán, thay đổi “chỉ thêm một subtype” vẫn có thể là **breaking change của giao thức** nếu phía nhận yêu cầu tất cả các biến thể đều phải được nhận diện.

## 11. Chiến lược thay đổi sealed hierarchy trong dự án thực tế

### 11.1. Trước khi thêm subtype

Xác định liệu trường hợp mới có thực sự khác biệt về **ngữ nghĩa** và **dữ liệu**. Nếu chỉ là khác biệt về cách hiển thị, có thể một field hoặc hành vi chung là đủ; nếu nó có vòng đời hoặc quy tắc nghiệp vụ riêng, một subtype mới có thể là lựa chọn rõ ràng hơn.

Tìm các nơi dùng kiểu cha làm tham số, kiểu trả về hoặc trường dữ liệu; đặc biệt quan sát các chuỗi `instanceof`, factory, serializer, map/registry theo loại, handlers, workflow và xử lý ngoại lệ dự phòng.

### 11.2. Khi thay đổi subtype

Giữ những kiểu con hiện có nếu chỉ đang mở rộng API. Đảm bảo subtype mới có modifier/trạng thái hợp lệ (`final`, `sealed` hoặc `non-sealed` theo quy tắc Java 17), được khai báo đúng trong `permits`, đúng package/module và mang dữ liệu cần thiết.

Nếu cần bỏ hoặc thay thế subtype, xác định chiến lược di chuyển rõ ràng cho client cũ và dữ liệu đã lưu. Đổi `permits` trước khi cập nhật những thành phần phụ thuộc có thể làm việc biên dịch hoặc triển khai thất bại.

### 11.3. Khi phát hành

Một trình tự thường hợp lý cho trường hợp **thêm** subtype trong nhiều dịch vụ:

1. Cập nhật hợp đồng và thông báo kiểu dữ liệu mới.
2. Nâng cấp các thành phần **đọc/nhận** để hiểu hoặc xử lý an toàn kiểu mới.
3. Sau đó bật các thành phần **ghi/gửi** tạo ra kiểu mới.
4. Theo dõi các lỗi liên quan kiểu chưa hỗ trợ và hành vi nghiệp vụ trong quá trình chuyển đổi.

Với trường hợp **bỏ** subtype, thông thường cần làm ngược lại về mặt dữ liệu: ngừng sinh thêm giá trị cũ, xử lý các giá trị cũ còn tồn tại, rồi mới rút kiểu khỏi API và các thành phần sử dụng. Trình tự cụ thể tùy hệ thống và hợp đồng giữa các nhóm.

### 11.4. Khi nâng cấp thư viện

Đảm bảo ứng dụng không vô tình trộn các class file của hai phiên bản không tương thích. Nếu phiên bản mới loại bỏ subtype nhưng một thư viện khác còn được biên dịch để triển khai subtype cũ, lỗi có thể chỉ xuất hiện khi JVM thực sự nạp tới lớp đó.

Quản lý phiên bản dependency, phát hành tài liệu migration và kiểm tra các luồng nghiệp vụ quan trọng giúp phát hiện tác động mà riêng bước biên dịch không chỉ ra được.

## 12. Khi nào không nên chọn `sealed`?

Sealed phù hợp nếu hệ phân cấp có **những trường hợp trực tiếp được kiểm soát có chủ đích**. Nó kém phù hợp khi thiết kế dự định cho các plugin hoặc ứng dụng bên ngoài tự bổ sung triển khai trực tiếp ở package/module của họ.

Trong API cần mở rộng công khai, có thể cân nhắc:

- Interface thông thường cho phép triển khai đa dạng.
- Một sealed hierarchy chỉ giới hạn các nhóm lớn, trong đó một nhánh `non-sealed` được dùng làm điểm mở rộng.
- Tách kiểu kết quả nội bộ thành sealed, còn hợp đồng plugin bên ngoài sử dụng interface riêng.

Đánh đổi là giữa **kiểm soát mô hình** và **khả năng mở rộng**. Chọn sealed giúp đọc và quản lý tập loại trực tiếp, nhưng cũng biến các thay đổi ở tập loại này thành thay đổi cần quản trị phiên bản cẩn thận.

## 13. Các câu hỏi thường gặp

**Thêm một tên mới vào `permits` có làm mọi client cũ lỗi biên dịch không?**  
Không. Với các chuỗi `if`/`instanceof` Java 17 như ví dụ, mã cũ thường vẫn biên dịch được. Nhưng khi nhận subtype mới, mã đó có thể không xử lý đúng.

**Có thể bỏ `default` hoặc nhánh dự phòng vì sealed interface chỉ có vài subtype không?**  
Điều đó phụ thuộc cấu trúc và cách xử lý. Với Java 17 ổn định, chuỗi `if`/`instanceof` không được trình biên dịch bảo đảm đã bao phủ tất cả trường hợp. Nhánh dự phòng thể hiện rõ chính sách khi gặp trường hợp ngoài dự kiến, đặc biệt khi API được nâng cấp.

**Một kiểu con không có trong `permits` có được tồn tại nếu đã biên dịch từ phiên bản cũ không?**  
Không thể coi là hợp lệ: JVM kiểm tra ràng buộc sealed khi liên kết/nạp kiểu. Binary subtype cũ có thể gây `IncompatibleClassChangeError` nếu supertype mới không còn cho phép nó.

**Thêm subtype gián tiếp có cần sửa `permits` của kiểu gốc không?**  
Không nhất thiết. Nếu subtype đó kế thừa qua một nhánh `non-sealed`, chỉ kiểu nhánh trực tiếp mới nằm trong danh sách `permits` của gốc.

**Có thể dùng `switch` pattern matching để trình biên dịch báo thiếu trường hợp trong Java 17 không?**  
Tính năng này còn là preview ở Java 17, nên nằm ngoài phạm vi API/cú pháp chính thức của bài học. Có thể dùng `instanceof` hoặc đa hình như minh họa.

**Khi nào thay đổi subtype cần phiên bản lớn?**  
Không có quy tắc cố định của Java về số phiên bản. Bỏ/đổi tên subtype, thay đổi hợp đồng dữ liệu hoặc khiến client không còn xử lý đúng một trường hợp là dấu hiệu cần đánh giá như breaking change theo quy tắc phát hành của thư viện hoặc hệ thống.

## 14. Tài liệu tham khảo chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): sealed classes và interfaces trở thành tính năng chính thức trong Java 17.
- [Java Language Specification 17, chương 8 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): giới hạn kiểu con trực tiếp, `permits`, `final`, `sealed`, `non-sealed`.
- [Java Language Specification 17, chương 9 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): sealed interfaces và permitted direct subinterfaces/implementations.
- [Java Language Specification 17, chương 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): đánh giá các thay đổi API tới binary đã biên dịch.
- [Java SE 17 API, `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isSealed()`, `getPermittedSubclasses()`.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): lý do không dùng `switch` pattern matching như cú pháp chính thức của Java 17.

**Nguyên tắc thiết kế:** Khi chỉnh sửa `permits`, hãy coi đó là thay đổi của hợp đồng kiểu và các luồng xử lý dữ liệu. Cùng với việc bảo đảm Java 17 biên dịch, cần xem xét consumer cũ, binary đã triển khai, dữ liệu lưu trữ và ý nghĩa nghiệp vụ của từng subtype.
