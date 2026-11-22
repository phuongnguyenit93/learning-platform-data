# Suy luận `permits` khi các kiểu con nằm cùng tệp nguồn trong Java 17

## 1. Vấn đề: `sealed` kiểm soát các kiểu con như thế nào?

Trong Java 17, `sealed class` và `sealed interface` cho phép kiểu cha **giới hạn chính xác những kiểu được trực tiếp kế thừa hoặc triển khai nó**. Thông thường, bạn sẽ gặp khai báo có `permits`:

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

`Result` chỉ cho phép `Success` và `Failure` là **kiểu con trực tiếp**. Một lớp khác tùy ý viết `implements Result` sẽ không được chấp nhận.

Tuy nhiên, khi hai kiểu con được khai báo **ngay trong cùng tệp mã nguồn** với `Result`, Java 17 cho phép bỏ hoàn toàn phần `permits Success, Failure`:

~~~java
sealed interface Result {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

Hai cách viết mang cùng ý nghĩa đối với danh sách kiểu con trực tiếp trong ví dụ trên. Ở cách thứ hai, trình biên dịch **tự suy luận `permits` từ những khai báo kiểu con trực tiếp nằm trong cùng compilation unit** (*đơn vị biên dịch*, trong tình huống thông thường chính là một tệp `.java`). Đây là tính năng chính thức và ổn định trong Java 17; bạn không cần bật preview.

> **Điểm cốt lõi:** Bỏ `permits` không có nghĩa là cho phép bất kỳ ai mở rộng `sealed`. Nó chỉ chuyển việc liệt kê các kiểu con trực tiếp từ lập trình viên sang trình biên dịch, dựa trên những khai báo đủ điều kiện **trong cùng tệp nguồn**.

## 2. Quy tắc suy luận `permits`

Giả sử một `sealed` type không khai báo `permits`. Java 17 xác định tập các kiểu được phép như sau:

1. Tìm các khai báo **lớp hoặc interface có tên hợp lệ** trong cùng compilation unit với kiểu `sealed`.
2. Chọn những kiểu **trực tiếp** dùng `extends` hoặc `implements` để kế thừa/triển khai chính kiểu `sealed` đó.
3. Tập các kiểu tìm được trở thành danh sách kiểu con trực tiếp được cho phép (*permitted direct subclasses/subinterfaces*).
4. Nếu không tìm được kiểu con trực tiếp nào để suy luận, việc khai báo `sealed` không có `permits` sẽ gây **lỗi biên dịch**.

Đối với `sealed class`, trình biên dịch xem các lớp có **direct superclass** là lớp `sealed`. Đối với `sealed interface`, trình biên dịch xem các lớp/record và interface có kiểu `sealed` đó trong danh sách **direct superinterfaces**. Các khai báo ở mức top-level và các kiểu thành viên (*member types*) đủ điều kiện đều có thể tham gia suy luận.

| Trường hợp | Có được tự suy luận vào `permits`? | Lý do |
|---|---|---|
| `final class B extends A` cùng tệp với `sealed class A` | Có | `B` trực tiếp kế thừa `A`. |
| `record R(...) implements I` cùng tệp với `sealed interface I` | Có | `R` trực tiếp triển khai `I`; record mặc nhiên `final`. |
| `non-sealed interface J extends I` cùng tệp với `sealed interface I` | Có | `J` là interface con trực tiếp của `I`. |
| `class C extends B`, trong đó `B extends A` | Không thuộc `permits` của `A` | `C` chỉ là kiểu con **gián tiếp** của `A`. |
| `class D` cùng tệp nhưng không `extends/implements A` | Không | Chỉ ở chung tệp chưa đủ điều kiện. |
| `class B extends A` nằm ở tệp `B.java` khác | Không được tự suy luận | Điều kiện cùng compilation unit không thỏa, dù có cùng thư mục hay package. |
| Lớp cục bộ trong phương thức hoặc lớp vô danh | Không | Không có canonical name để làm kiểu con được phép. |

Ngoài việc có tên trong tập cho phép, mỗi kiểu con trực tiếp phải nêu rõ cách tiếp tục nhánh kế thừa:

- `final`: không cho phép tạo lớp con tiếp theo.
- `sealed`: tiếp tục kiểm soát tập kiểu con trực tiếp của chính nhánh đó.
- `non-sealed`: mở nhánh cho các lớp/interface kế thừa tiếp theo theo quy tắc Java thông thường.

**Ngoại lệ về cú pháp thường dùng:** `record` mặc nhiên là `final`, vì thế không cần và không thể ghi thêm `final` trước `record`. Ví dụ trong bài sử dụng record để biểu diễn những kết quả bất biến.

## 3. Ví dụ chạy được: hai `record` nằm cùng tệp với `sealed interface`

Tạo thư mục dự án và tệp `src/demo/Demo.java` như sau:

~~~text
sealed-inference/
└── src/
    └── demo/
        └── Demo.java
~~~

Nội dung **toàn bộ** tệp `src/demo/Demo.java`:

~~~java
package demo;

public class Demo {
    public static void main(String[] args) {
        Result first = new Success("saved");
        Result second = new Failure("disk is full");

        System.out.println(describe(first));
        System.out.println(describe(second));
    }

    private static String describe(Result result) {
        if (result instanceof Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.reason();
        }
        throw new IllegalStateException("Unknown result");
    }
}

// Không cần ghi: permits Success, Failure
sealed interface Result {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

### Điều gì được suy luận?

Trong `Demo.java`, ba khai báo `Result`, `Success` và `Failure` thuộc **cùng một đơn vị biên dịch**. `Success` và `Failure` đều khai báo `implements Result` trực tiếp. Do đó, trình biên dịch xử lý danh sách được phép tương đương:

~~~java
sealed interface Result permits Success, Failure {
}
~~~

Phần `permits` phía trên chỉ dùng để minh họa sự tương đương; **không cần thêm nó** vào ví dụ gốc. Khai báo `Demo` trong cùng tệp không nằm trong tập được phép, vì `Demo` không triển khai `Result`.

Hai record vẫn phải viết `implements Result`: suy luận `permits` **không tự tạo** quan hệ kế thừa. Trình biên dịch chỉ đọc các quan hệ kế thừa được khai báo sẵn. Việc record mặc nhiên `final` đáp ứng yêu cầu đối với kiểu con trực tiếp của một kiểu `sealed`.

Phương thức `describe` dùng **pattern matching for `instanceof`**, tính năng đã ổn định trước Java 17. Bài này không dùng pattern matching for `switch` vì tính năng đó còn ở dạng preview trong Java 17.

### Biên dịch và chạy bằng dòng lệnh

Đứng tại thư mục gốc `sealed-inference` và tạo sẵn thư mục `src/demo`, sau đó lưu file `Demo.java` theo đường dẫn trên.

Trên PowerShell (Windows), có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force -Path src/demo | Out-Null
~~~

Trên Bash/Zsh (Linux/macOS):

~~~bash
mkdir -p src/demo
~~~

Sau khi lưu mã nguồn, dùng lệnh giống nhau trên cả hai môi trường:

~~~text
javac --release 17 -encoding UTF-8 -d out src/demo/Demo.java
java -cp out demo.Demo
~~~

Kết quả:

~~~text
Success: saved
Failure: disk is full
~~~

`javac` biên dịch cả các top-level type được khai báo trong `Demo.java`; ngoài `Demo.class`, trong `out/demo` còn có `Result.class`, `Success.class` và `Failure.class`. Mặc dù chỉ có một tệp `.java`, có **nhiều kiểu Java** và do đó có thể tạo ra nhiều tệp `.class`.

Tên tệp là `Demo.java` vì `Demo` là kiểu top-level duy nhất có `public`. Các kiểu còn lại không khai báo `public` và có phạm vi truy cập mức package. Trong thực tế, cách gộp này phù hợp khi một họ kiểu nhỏ chỉ phục vụ mã trong cùng package.

## 4. Suy luận với `sealed class`: phân biệt kiểu con trực tiếp và gián tiếp

Quy tắc suy luận cũng áp dụng cho **lớp `sealed`**, không chỉ interface. Xét tệp `Vehicle.java` độc lập:

~~~java
public sealed abstract class Vehicle {
}

final class Bicycle extends Vehicle {
}

non-sealed class MotorVehicle extends Vehicle {
}

final class Taxi extends MotorVehicle {
}
~~~

Mặc dù cả bốn lớp nằm chung một tệp, danh sách được suy luận cho `Vehicle` chỉ là:

~~~java
public sealed abstract class Vehicle permits Bicycle, MotorVehicle {
}
~~~

Sơ đồ quan hệ:

~~~text
Vehicle (sealed)
├── Bicycle (final)           [trực tiếp, được suy luận]
└── MotorVehicle (non-sealed) [trực tiếp, được suy luận]
    └── Taxi (final)          [gián tiếp, không thuộc permits của Vehicle]
~~~

`Taxi` không nằm trong `permits` của `Vehicle` vì nó kế thừa `MotorVehicle`, **không trực tiếp `extends Vehicle`**. Việc `MotorVehicle` khai báo `non-sealed` mở nhánh này cho các kiểu con tiếp theo. Quy tắc `sealed` kiểm soát **cạnh kế thừa trực tiếp**; nó không nhất thiết đóng kín toàn bộ cây kế thừa ở mọi cấp.

Nếu thay `MotorVehicle` thành một lớp `sealed` thì chính lớp đó phải có danh sách kiểu con được phép, tường minh hoặc suy luận theo quy tắc cùng tệp. Ngược lại, khi dùng `final`, không thể khai báo bất kỳ lớp con nào của lớp `final`.

## 5. Kiểu lồng nhau cũng có thể được suy luận

“Cùng tệp nguồn” không chỉ có nghĩa là đặt nhiều top-level type kế tiếp nhau. Các **member type** được khai báo bên trong kiểu `sealed` cũng thuộc cùng compilation unit. Ví dụ tệp `Outcome.java`:

~~~java
public sealed interface Outcome {
    record Ok(int value) implements Outcome {
    }

    record Error(String message) implements Outcome {
    }
}
~~~

Đây là một `sealed interface` hợp lệ, tương đương với việc khai báo:

~~~java
public sealed interface Outcome permits Outcome.Ok, Outcome.Error {
    record Ok(int value) implements Outcome {
    }

    record Error(String message) implements Outcome {
    }
}
~~~

`Outcome.Ok` và `Outcome.Error` là các **member record** có tên chuẩn (*canonical name*) và trực tiếp `implements Outcome`, vì thế chúng có thể được suy luận. Trong Java, member type khai báo bên trong interface mặc nhiên là `public static`; người dùng có thể tạo đối tượng với cú pháp:

~~~java
Outcome result = new Outcome.Ok(42);
~~~

Cách đặt các record lồng trong interface giúp nhóm một họ kết quả nhỏ ngay tại nơi định nghĩa contract. Nếu kiểu con cần trở thành API công khai lớn, có nhiều thành phần hoặc cần duy trì độc lập, tách thành tệp riêng và khai báo `permits` tường minh thường dễ quản lý hơn.

**Giới hạn quan trọng:** Không áp dụng suy luận cho *local class* nằm trong thân phương thức và *anonymous class*, vì các loại này không có canonical name. Hãy dùng top-level type hoặc member type được đặt tên khi thiết kế họ `sealed`.

## 6. Sự khác biệt khi chuyển kiểu con sang tệp khác

Đây là tình huống dễ nhầm lẫn nhất. Giả sử lúc đầu `Result`, `Success` và `Failure` cùng nằm trong `Demo.java` và biên dịch thành công. Sau đó bạn tổ chức lại mã thành:

~~~text
src/demo/
├── Result.java
├── Success.java
└── Failure.java
~~~

Nếu nội dung `Result.java` vẫn là:

~~~java
package demo;

public sealed interface Result {
}
~~~

còn `Success.java` chứa:

~~~java
package demo;

public record Success(String value) implements Result {
}
~~~

và `Failure.java` chứa:

~~~java
package demo;

public record Failure(String reason) implements Result {
}
~~~

thì **không thể tiếp tục dựa vào suy luận `permits`**. `Success` và `Failure` nằm ở các compilation unit khác `Result`, dù cả ba tệp cùng package `demo`. Trình biên dịch sẽ báo lỗi liên quan đến kiểu `sealed` không có kiểu con được phép suy luận, và/hoặc kiểu trực tiếp triển khai nhưng không thuộc danh sách cho phép.

Để sửa, khai báo rõ trong **`Result.java`**:

~~~java
package demo;

public sealed interface Result permits Success, Failure {
}
~~~

Giữ nguyên `Success.java` và `Failure.java` như trên. Có thể biên dịch các tệp:

~~~text
javac --release 17 -encoding UTF-8 -d out src/demo/Result.java src/demo/Success.java src/demo/Failure.java
~~~

Lúc này, `permits` nói rõ kiểu con được phép dù các lớp được đặt ở **các tệp mã nguồn khác nhau**. Nếu thêm `record Pending() implements Result` ở một tệp thứ tư, bạn cũng phải bổ sung `Pending` vào `permits`. Khi `permits` được viết tường minh, trình biên dịch **không tự ghép thêm** kiểu con khác, kể cả kiểu đó cùng tệp.

### Cùng package, cùng module và cùng tệp có phải là một?

Không. Đây là ba phạm vi khác nhau:

| Khái niệm | Mô tả | Có đủ để tự suy luận khi bỏ `permits`? |
|---|---|---|
| Cùng package | Nhiều kiểu cùng khai báo `package demo;`. | **Không**, nếu chúng nằm ở các tệp `.java` khác nhau. |
| Cùng named module | Nhiều package/tệp có thể thuộc một module. | **Không**, nếu khác compilation unit. |
| Cùng compilation unit | Các khai báo kiểu thuộc cùng một đơn vị biên dịch, thường là một tệp `.java`. | **Có**, khi đồng thời thỏa điều kiện kiểu con trực tiếp và có canonical name. |

Khi dùng `permits` tường minh, các kiểu trực tiếp được phép vẫn phải đáp ứng ràng buộc tổ chức của Java 17: nếu kiểu `sealed` thuộc **named module**, các kiểu được phép phải thuộc **cùng module**; nếu thuộc **unnamed module**, chúng phải thuộc **cùng package**. Quy tắc này độc lập với việc có thể bỏ `permits` hay không.

## 7. Các lỗi tư duy và lỗi biên dịch thường gặp

### 7.1. Quên `final`, `sealed` hoặc `non-sealed` ở kiểu con

~~~java
sealed class Animal {
}

class Dog extends Animal {
}
~~~

`Dog` nằm cùng tệp và là kiểu con trực tiếp nên có thể được suy luận vào tập cho phép. Tuy nhiên, **vẫn lỗi biên dịch** vì lớp `Dog` chưa chỉ rõ cách kiểm soát nhánh kế thừa. Sửa thành `final class Dog extends Animal`, hoặc chọn `sealed`/`non-sealed` phù hợp với thiết kế.

Với `record` như `record Dog(String name) implements AnimalView` (khi `AnimalView` là một `sealed interface`), bản thân record đã mặc nhiên `final`, nên không phải thêm modifier.

### 7.2. Không có kiểu con trực tiếp nào trong cùng tệp

~~~java
sealed interface EmptyResult {
}
~~~

Khai báo trên không có `permits` và cũng không có kiểu con để suy luận, do đó không hợp lệ. Một kiểu `sealed` phải chỉ ra được ít nhất một kiểu con trực tiếp được phép, bằng `permits` tường minh hoặc bằng suy luận.

### 7.3. Có một kiểu cùng tệp nhưng không trực tiếp kế thừa

~~~java
sealed interface Response {
}

final class Helper {
}
~~~

`Helper` không `implements Response`, nên không được suy luận. Chỉ “đặt cùng tệp” không tạo nên quan hệ kiểu con. Ví dụ vẫn lỗi vì `Response` chưa có kiểu con trực tiếp được phép.

### 7.4. Nhầm kiểu con gián tiếp với kiểu con trực tiếp

~~~java
sealed class Base {
}

non-sealed class Child extends Base {
}

final class Grandchild extends Child {
}
~~~

`Base` chỉ suy luận `Child`; `Grandchild` là kiểu con gián tiếp. Không cần, và cũng không được, thêm `Grandchild` vào `permits` của `Base` vì `Grandchild` không trực tiếp `extends Base`.

### 7.5. Tưởng rằng bỏ `permits` thì có thể mở rộng ở tệp khác

~~~java
// Tệp Base.java
public sealed class Base {
}

// Tệp External.java
public final class External extends Base {
}
~~~

Đoạn mã minh họa hai **tệp độc lập**; trình biên dịch không tự suy luận `External` thành kiểu con hợp lệ của `Base`. Nếu muốn tách hai lớp thành hai tệp riêng, cần khai báo `public sealed class Base permits External` (và bảo đảm ràng buộc package/module). Nếu chỉ có một kiểu con, vẫn phải viết `permits` khi kiểu đó ở tệp khác.

### 7.6. Trùng lặp hoặc liệt kê sai trong `permits`

Khi ghi `permits` tường minh, mỗi tên kiểu chỉ được liệt kê một lần và phải là kiểu con **trực tiếp** có thể truy cập được. Ví dụ, nếu `C extends B` và `B extends A`, câu lệnh `sealed class A permits B, C` là sai đối với `C`. Viết `permits` cũng yêu cầu kiểu cha thật sự có modifier `sealed`.

### 7.7. Hiểu nhầm thông tin trong tệp `.class`

Suy luận `permits` là một quy tắc của **mã nguồn khi biên dịch**. Sau khi biên dịch, giới hạn kiểu con được lưu vào metadata của bytecode, cụ thể là thuộc tính `PermittedSubclasses`. JVM có thể áp dụng giới hạn đó khi tải/liên kết các lớp; đây không phải quy ước chỉ có tác dụng lúc biên dịch mã nguồn.

Bạn có thể nghiên cứu metadata của kiểu đã biên dịch bằng công cụ `javap` thuộc JDK, chẳng hạn:

~~~text
javap -v -classpath out demo.Result
~~~

Khi xem kết quả chi tiết, tìm thuộc tính `PermittedSubclasses` để hiểu giới hạn mà trình biên dịch đã ghi. Việc không thấy chữ `permits` trong tệp `.java` **không** làm mất thông tin giới hạn này.

## 8. Khi nào nên tận dụng suy luận, khi nào nên viết `permits`?

**Nên tận dụng suy luận** khi họ kiểu có phạm vi nhỏ, các kiểu con được định nghĩa gần nhau trong cùng tệp, và việc thêm một kiểu con trực tiếp là thay đổi có chủ đích. Ví dụ hợp lý gồm:

- Một `sealed interface` mô hình hóa hai hoặc ba kết quả, mỗi kết quả là một record nhỏ.
- Các member record bên trong một `sealed interface` duy nhất.
- Một lớp `sealed` và một vài nhánh con nhỏ được quản lý trong cùng tệp.

**Nên ghi `permits` tường minh** khi các kiểu con đã được tách thành nhiều tệp, khi xây dựng API có cấu trúc phức tạp hơn hoặc khi bạn muốn người đọc nhìn thấy danh sách kiểu con ngay trong khai báo cha. Cần nhớ việc suy luận tự động phụ thuộc **vị trí khai báo trong mã nguồn**, vì vậy khi chuyển một kiểu con ra tệp mới, bạn phải cập nhật thiết kế `permits`.

| Điểm so sánh | Bỏ `permits` để suy luận | Ghi `permits` tường minh |
|---|---|---|
| Nguồn danh sách được phép | Các kiểu con trực tiếp có tên hợp lệ trong **cùng compilation unit**. | Các tên được liệt kê trong khai báo `permits`. |
| Khi thêm kiểu con trong cùng tệp | Được tự tính vào tập cho phép nếu thỏa điều kiện. | Phải cập nhật danh sách `permits`. |
| Khi chuyển kiểu con sang tệp khác | Không còn được suy luận; cần khai báo tường minh. | Vẫn có thể hợp lệ nếu ràng buộc module/package được thỏa. |
| Yêu cầu modifier ở kiểu con | Vẫn bắt buộc `final`, `sealed` hoặc `non-sealed` theo loại khai báo; record mặc nhiên `final`. | Giống hệt. |
| Ý nghĩa tại runtime | Vẫn là kiểu `sealed` với tập con được phép. | Giống hệt. |

## 9. Bài tập vận dụng

**Bài tập 1 — Dự đoán tập được suy luận**

Xét các khai báo cùng nằm trong `Status.java`:

~~~java
sealed interface Status {
}

record Active(int code) implements Status {
}

record Disabled(String reason) implements Status {
}

final class Printer {
}
~~~

Hãy xác định danh sách tương đương với `permits` của `Status`. Giải thích vì sao `Printer` không xuất hiện.

**Bài tập 2 — Xác định lỗi khi tách tệp**

Chuyển `Active` sang `Active.java` trong cùng package với `Status.java` và giữ `Disabled` lại cùng `Status`. Nếu vẫn để `sealed interface Status {}`, điều gì xảy ra khi biên dịch `Active.java`? Bạn cần thay khai báo `Status` thành dạng nào để chấp nhận cả hai kiểu con?

**Bài tập 3 — Tìm các kiểu con trực tiếp**

~~~java
sealed class Document {
}

final class TextDocument extends Document {
}

non-sealed class MediaDocument extends Document {
}

final class ImageDocument extends MediaDocument {
}
~~~

Hãy vẽ cây kế thừa, liệt kê `permits` suy luận của `Document` và giải thích liệu một `AudioDocument extends MediaDocument` có thể được bổ sung hay không.

**Bài tập 4 — Thiết kế kiểu lồng nhau**

Tạo một `sealed interface ApiResponse` có hai member record `Ok(String data)` và `Error(int code, String message)` trong cùng tệp `ApiResponse.java`. Không viết `permits`; tạo lần lượt hai đối tượng bằng tên `ApiResponse.Ok` và `ApiResponse.Error` từ một lớp chạy thử.

### Gợi ý tự đối chiếu

- Bài 1: Tập trực tiếp là `Active` và `Disabled`. `Printer` không `implements Status`.
- Bài 2: `Active` nằm khác compilation unit nên không được suy luận; `Status` phải khai báo `permits Active, Disabled`, dù `Disabled` vẫn cùng tệp.
- Bài 3: Tập của `Document` chỉ gồm `TextDocument` và `MediaDocument`. `ImageDocument` là kiểu con gián tiếp. Vì `MediaDocument` là `non-sealed`, có thể tạo thêm `AudioDocument extends MediaDocument`.
- Bài 4: Hai member record có tên chuẩn và trực tiếp triển khai `ApiResponse`, nên được suy luận; record mặc nhiên `final`.

## 10. Ghi nhớ quy tắc

Một cách ghi nhớ chính xác cho Java 17:

> **`sealed` không có `permits` → lấy các kiểu con *trực tiếp*, có *canonical name*, được khai báo trong *cùng compilation unit*.** Các kiểu con trực tiếp vẫn phải khai báo trạng thái `final`, `sealed` hoặc `non-sealed` phù hợp.

Ba điều kiện **cùng tệp, quan hệ kế thừa trực tiếp, và kiểu có tên hợp lệ** là cốt lõi của suy luận. Dù danh sách được viết tay hay được trình biên dịch suy luận, `sealed` vẫn giới hạn những kiểu có thể trực tiếp mở rộng contract.

### Tài liệu tham khảo

- [Java SE 17 Language Specification — Section 8.1.6: Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [Java SE 17 Language Specification — Section 9.1.4: Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).
- [Oracle Java 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html).
