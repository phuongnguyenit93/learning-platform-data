# Thông tin suy ra từ bytecode và dữ liệu gỡ lỗi trong chẩn đoán null

## 1. Mục tiêu: JVM biết được điều gì khi xảy ra NullPointerException?

Khi Java gặp một tham chiếu `null` ở vị trí cần đối tượng, JVM có thể tạo ra một `NullPointerException` (NPE). Với các JVM hỗ trợ **Helpful NullPointerExceptions** (JEP 358), thông báo không chỉ nói rằng có NPE mà còn thường mô tả:

1. **Thao tác thất bại**: gọi phương thức, đọc trường, ghi trường hay truy cập mảng nào.
2. **Biểu thức đã cung cấp tham chiếu `null`** cho thao tác ấy: một biến cục bộ, một chuỗi trường, giá trị trả về của lời gọi phương thức hoặc tham chiếu mảng.

Ví dụ, xét:

```java
User user = new User(null);
return user.profile.email.length();
```

Nếu `user.profile` là `null`, JVM không thể đọc trường `email`. Trên HotSpot hiện đại với thông báo chi tiết được bật và có thông tin tên biến, ta có thể thấy:

```text
Cannot read field "email" because "user.profile" is null
```

Thông báo chỉ ra **nơi biểu thức bị hỏng**, không tự giải thích **vì sao giá trị trở thành `null`** (chưa gán, thiếu dữ liệu từ API, mapping sai, lỗi nghiệp vụ...).

**Bối cảnh phiên bản:** JEP 358 xuất hiện trong Java 14. Ở bản Java 14, tùy chọn chi tiết **tắt theo mặc định**; từ Java 15, HotSpot bật mặc định. Trên JDK 17+ hiện nay, đây là cơ chế chẩn đoán thực tế còn áp dụng, không phải tính năng preview cần kích hoạt. Bài học tập trung vào **cách JVM khai thác bytecode và metadata debug** chứ không đi sang các tính năng Java không còn phù hợp.

## 2. JVM suy luận từ bytecode thay vì đọc lại mã nguồn

Trình biên dịch `javac` biến tệp `.java` thành các tệp `.class` chứa **bytecode JVM**. Khi chạy, HotSpot thực hiện các chỉ thị bytecode (có thể được biên dịch JIT thành mã máy), và trong lúc tạo thông điệp NPE chi tiết, nó có thể phân tích **bytecode liên quan đến vị trí phát sinh ngoại lệ**.

Hãy hình dung biểu thức:

```java
int n = user.profile.email.length();
```

Nếu so từng bước, cần:

1. Lấy tham chiếu `user`.
2. Đọc trường `profile` từ `user`.
3. Đọc trường `email` từ đối tượng `profile`.
4. Gọi `length()` trên đối tượng `String` thu được.

Nếu bước 3 gặp `profile == null`, thao tác đọc trường `email` gây NPE. Nếu `profile` khác `null` nhưng `email == null`, thao tác gọi `length()` mới gây NPE. Hai lỗi có thể xảy ra trên **cùng một dòng nguồn**, nhưng thông điệp chi tiết có thể phân biệt chính xác **bước đang thất bại**.

### Những chỉ thị bytecode tiêu biểu

| Chỉ thị / nhóm chỉ thị | Ý nghĩa khái quát | JVM có thể sử dụng để chẩn đoán |
| --- | --- | --- |
| `aload`, `aload_0`, ... | Nạp tham chiếu từ một slot biến cục bộ | Nguồn của tham chiếu có thể là `<local0>` hoặc tên biến khi metadata có sẵn |
| `getfield` | Đọc trường của một đối tượng | Tên trường đang đọc, ví dụ `email`; tham chiếu đối tượng nhận có thể là `null` |
| `putfield` | Ghi trường của một đối tượng | Tên trường không thể ghi nếu đối tượng nhận là `null` |
| `invokevirtual`, `invokeinterface` | Gọi phương thức instance | Tên/chữ ký phương thức không thể gọi vì receiver là `null` |
| `arraylength` | Lấy độ dài của mảng | Tham chiếu mảng là `null` |
| `aaload`, `iaload` và các biến thể load/store mảng | Truy cập phần tử mảng | Không thể đọc/ghi phần tử vì tham chiếu mảng là `null` |

Đây là sơ đồ **diễn giải cơ chế**, không phải khẳng định rằng mọi phép toán nguồn luôn được dịch thành đúng một chỉ thị duy nhất. Trình biên dịch có thể phát sinh chuỗi bytecode phức tạp hơn. Khi được hỗ trợ, thông điệp NPE mô tả chuỗi thao tác dựa trên bytecode **đang có trong class file**, không phải một phép “đọc ngược” đầy đủ toàn bộ văn bản Java.

### Bytecode index và vị trí lỗi

Một phương thức trong `.class` có chuỗi chỉ thị; **bytecode index (BCI)** là vị trí một chỉ thị trong mã bytecode của phương thức. JVM có thể dựa trên vị trí gây NPE và phân tích ngược biểu thức cung cấp tham chiếu `null` cho chỉ thị tương ứng.

Điều này giải thích vì sao nhiều phép truy cập nằm trên **cùng dòng nguồn** vẫn có thể được phân biệt. Đừng lẫn BCI với **số dòng trong file `.java`**: BCI nằm ở cấp bytecode, còn số dòng nguồn phụ thuộc metadata gỡ lỗi `LineNumberTable`.

## 3. Hai loại thông tin: bytecode và debug metadata

Một điểm dễ nhầm là câu “không có debug info thì JVM không biết gì”. Điều đó **không đúng**.

### 3.1. Bytecode cung cấp cấu trúc thao tác

Dù không có tên biến cục bộ ở mã nguồn, bytecode vẫn cho JVM biết:

- Chỉ thị nào đang gặp tham chiếu `null`.
- Đang đọc/ghi **trường nào** (`email`, `profile`).
- Đang gọi **phương thức nào** (`String.length()`).
- Tham chiếu được lấy từ **slot biến cục bộ nào** hoặc một chuỗi thao tác nào.

Tên trường và thông tin tham chiếu phương thức nằm trong cấu trúc class file, **không đòi hỏi tên biến cục bộ phải có trong bảng debug**. Vì vậy, NPE chi tiết vẫn thường được tạo khi ứng dụng được biên dịch không có thông tin debug cho biến.

### 3.2. LocalVariableTable giúp có tên biến nguồn

Bytecode thực hiện `aload` trên **slot số**; tên biến như `nickname` hay `user` thường là dữ liệu dành cho người đọc, không cần thiết để JVM thực thi.

Bảng `LocalVariableTable` (metadata tùy chọn trong tệp `.class`) có thể ánh xạ slot và phạm vi sống của biến với **tên biến ở nguồn**. Nếu bảng này tồn tại và đủ thông tin, HotSpot có thể dùng tên `nickname` thay vì ký hiệu `<local0>`.

Ví dụ cùng lỗi:

```java
static int localFailure() {
    String nickname = null;
    return nickname.length();
}
```

Khi có tên biến trong `LocalVariableTable`, thông báo điển hình:

```text
Cannot invoke "String.length()" because "nickname" is null
```

Khi thiếu tên biến, JVM vẫn mô tả được thao tác nhưng có thể dùng tên slot tổng hợp:

```text
Cannot invoke "String.length()" because "<local0>" is null
```

**Không nên suy ra rằng `<local0>` là tên biến thật**. Đó là cách mô tả vị trí lưu tham chiếu ở cấp JVM, không phải tên có thể tìm bằng Ctrl+F trong mã nguồn.

### 3.3. LineNumberTable và SourceFile phục vụ stack trace

Các metadata gỡ lỗi khác có vai trò riêng:

| Thành phần class file | Thông tin mang theo | Lợi ích |
| --- | --- | --- |
| Bytecode (`Code`) | Chỉ thị và các tham chiếu đến trường, phương thức, slot | Nguồn chính để xác định **thao tác gây NPE** |
| `LocalVariableTable` | Tên và phạm vi sống biến cục bộ | Thông báo có thể ghi tên `nickname` thay `<local0>` |
| `LineNumberTable` | Ánh xạ BCI tới số dòng nguồn | Stack trace có thể hiển thị `Class.java:42` |
| `SourceFile` | Tên tệp nguồn | Stack trace có thể nêu `Class.java` |

**Thông điệp `getMessage()` không đồng nghĩa stack trace**. `getMessage()` cung cấp mô tả lỗi; `printStackTrace()` hiển thị thêm ngữ cảnh phương thức/tệp/dòng nếu có dữ liệu tương ứng.

Việc JVM giải thích được `Cannot read field "email"` **không chứng minh** tệp `.class` còn nguyên mã nguồn hoặc được biên dịch bằng tùy chọn `-g`. Ngược lại, có file debug đầy đủ cũng không bảo đảm JVM tái tạo chính xác mọi biểu thức nguồn phức tạp.

## 4. `javac` tạo và bỏ metadata gỡ lỗi như thế nào?

Trên Java 17+, lệnh biên dịch có các lựa chọn liên quan:

| Lệnh | Thông tin gỡ lỗi trong `.class` |
| --- | --- |
| `javac Example.java` | Mặc định `javac` thường giữ **số dòng và tên tệp**, nhưng **không** giữ bảng tên biến cục bộ |
| `javac -g Example.java` | Tạo thông tin debug đầy đủ, gồm tên biến cục bộ |
| `javac -g:vars Example.java` | Yêu cầu thông tin debug của biến cục bộ (không mặc định thêm tất cả loại khác) |
| `javac -g:none Example.java` | Không sinh metadata debug tùy chọn như bảng dòng, tên tệp, tên biến |
| `javap -c -l Example` | Xem bytecode và các thông tin dòng/biến nếu có trong class file |

Đây là những tùy chọn **hiện hành**. `-g:none` không làm xóa bytecode; nó chủ yếu loại những metadata không cần cho việc thực thi. Vì vậy HotSpot vẫn có thể phân tích NPE dựa trên các chỉ thị còn tồn tại.

**Lưu ý thực tế:** Công cụ build (IDE, Maven, Gradle...) có thể tự chọn chính sách debug khác với lệnh `javac` gọi trực tiếp. Hãy xem cấu hình build thật, không suy đoán chỉ vì ứng dụng được biên dịch từ Java 17+.

### Xem bằng `javap`

Sau khi biên dịch:

```bash
javac --release 17 -g HelpfulNpeDetailsDemo.java
javap -c -l -p HelpfulNpeDetailsDemo
```

Trong kết quả `javap`, tìm:

- Phần `Code:` chứa các chỉ thị bytecode.
- `LineNumberTable:` cho phép liên kết vị trí bytecode với dòng mã nguồn.
- `LocalVariableTable:` ghi các cột như `Start`, `Length`, `Slot`, `Name`, `Signature`.

Để xem bytecode của một lớp lồng nhau `User`/`Profile` có thể phải xem `.class` tương ứng của lớp lồng nhau; tên tệp phụ thuộc cách Java đặt tên class file. Ví dụ bài chính bên dưới chủ yếu cần xem phương thức `localFailure` và `chainFailure` nằm trong lớp ngoài.

Sau khi chạy lại `javac --release 17 -g:none ...`, lệnh `javap -c -l` vẫn hiển thị phần bytecode `Code:` nhưng không còn các bảng debug mà `-g:none` đã loại bỏ.

## 5. Chương trình Java 17+ hoàn chỉnh: so sánh có và không có debug info

Lưu toàn bộ chương trình dưới đây vào tệp **`HelpfulNpeDetailsDemo.java`**:

```java
public class HelpfulNpeDetailsDemo {
    static final class Profile {
        String email;
        Profile(String email) { this.email = email; }
    }

    static final class User {
        Profile profile;
        User(Profile profile) { this.profile = profile; }
    }

    static int localFailure() {
        String nickname = null;
        return nickname.length();
    }

    static int chainFailure() {
        User user = new User(null);
        return user.profile.email.length();
    }

    static int methodFailure() {
        User user = new User(new Profile(null));
        return user.profile.email.length();
    }

    static int arrayFailure() {
        int[] values = null;
        return values.length;
    }

    static void explicitFailure() {
        throw new NullPointerException("missing value");
    }

    static void report(String label, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException e) {
            System.out.println(label + " => " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        report("local", HelpfulNpeDetailsDemo::localFailure);
        report("chain", HelpfulNpeDetailsDemo::chainFailure);
        report("method", HelpfulNpeDetailsDemo::methodFailure);
        report("array", HelpfulNpeDetailsDemo::arrayFailure);
        report("explicit", HelpfulNpeDetailsDemo::explicitFailure);
    }
}
```

Chương trình dùng **chính các đường đi gây NPE** để minh họa. Mỗi lời gọi nằm trong `report(...)`, nên NPE được bắt và ta có thể đọc `getMessage()`; không có exception nào làm chương trình dừng giữa chừng.

### 5.1. Biên dịch có thông tin gỡ lỗi đầy đủ

```bash
javac --release 17 -g HelpfulNpeDetailsDemo.java
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeDetailsDemo
```

**Đầu ra đã xác minh trên OpenJDK/HotSpot với tùy chọn hiện chi tiết:**

```text
local => Cannot invoke "String.length()" because "nickname" is null
chain => Cannot read field "email" because "user.profile" is null
method => Cannot invoke "String.length()" because "user.profile.email" is null
array => Cannot read the array length because "values" is null
explicit => missing value
```

Cách giải thích:

1. **`local`:** Biến `nickname` mang giá trị `null` và bị gọi `length()`. Vì có `LocalVariableTable`, thông điệp dùng tên biến nguồn.
2. **`chain`:** `user` khác `null` nhưng `user.profile` là `null`; NPE xảy ra khi cố **đọc trường `email`**, chưa đến bước gọi `length()`.
3. **`method`:** `user.profile` đã có đối tượng, còn `user.profile.email` là `null`; NPE xảy ra khi cố **gọi `String.length()`**.
4. **`array`:** Thao tác lấy thuộc tính `length` của một mảng có tham chiếu `null` tạo NPE do JVM; thông điệp chỉ ra thao tác đọc độ dài mảng.
5. **`explicit`:** Chương trình **chủ động** tạo `new NullPointerException("missing value")`. `getMessage()` trả đúng chuỗi được truyền vào constructor, không cần JVM suy ra biểu thức lỗi.

Lưu ý đầu ra này là **kết quả thực nghiệm trên JVM cụ thể**, dùng để học cơ chế và kiểm tra. Cách trình bày, cách viết tên kiểu, dấu nháy kép hoặc mức chi tiết có thể thay đổi theo bản JDK và implementation, nên **không viết bài kiểm thử phụ thuộc cứng vào toàn bộ thông báo NPE của mọi JVM**.

### 5.2. Biên dịch lại cùng chương trình nhưng không có debug info

```bash
javac --release 17 -g:none HelpfulNpeDetailsDemo.java
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeDetailsDemo
```

**Đầu ra đã xác minh trên cùng JVM:**

```text
local => Cannot invoke "String.length()" because "<local0>" is null
chain => Cannot read field "email" because "<local0>.profile" is null
method => Cannot invoke "String.length()" because "<local0>.profile.email" is null
array => Cannot read the array length because "<local0>" is null
explicit => missing value
```

So sánh hai lần chạy:

- Thông điệp vẫn biết **không thể gọi `length()`, đọc `email` hoặc lấy độ dài mảng**. Thông tin đó đến từ phân tích bytecode.
- Tên biến nguồn `nickname`, `user`, `values` không còn có mặt qua bảng debug, nên JVM minh họa bằng slot `<local0>`.
- **Tên các trường như `profile` và `email` vẫn được giữ trong đường dẫn mô tả** vì cấu trúc truy cập trường nằm trong bytecode/class file.
- Thông điệp của NPE **được ném tường minh** vẫn là `missing value`, vì đó là chuỗi lập trình viên cung cấp.
- Với `-g:none`, một stack trace đầy đủ cũng có thể không còn thông tin **tên tệp và số dòng nguồn**. Đó là ảnh hưởng khác với việc có/không có thông điệp NPE chi tiết.

**Lưu ý thao tác:** Nếu bạn muốn kiểm tra cả bảng debug và mã bytecode, hãy chạy `javap -c -l -p HelpfulNpeDetailsDemo` **sau mỗi lần biên dịch** và quan sát sự khác nhau, thay vì dùng nội dung `.class` từ lần biên dịch trước.

## 6. Cấu hình JVM: chi tiết NPE có thể bị tắt

Trong Java 17 và các bản HotSpot hiện đại, tùy chọn sau được **bật mặc định** theo tài liệu `java`:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeDetailsDemo
```

Để tắt chi tiết trong môi trường cần hạn chế thông tin lộ ra:

```bash
java -XX:-ShowCodeDetailsInExceptionMessages HelpfulNpeDetailsDemo
```

Đây là **tùy chọn khi khởi động JVM**, khác với cờ `-g` lúc biên dịch:

- `-g` / `-g:none` tác động lên **metadata trong `.class`**.
- `-XX:+ShowCodeDetailsInExceptionMessages` / `-XX:-ShowCodeDetailsInExceptionMessages` điều khiển khả năng JVM tạo **thông điệp NPE chi tiết**.

Nếu tắt chi tiết, NPE do JVM tạo mà không có thông điệp tường minh có thể cho `getMessage() == null`; khi dùng phép nối chuỗi của Java, giá trị `null` đó được in dưới dạng chữ `null`. Riêng NPE được tạo với `"missing value"` vẫn có thông điệp tường minh.

**Đừng quay lại khuyến nghị Java 14 “phải luôn thêm dấu + mới có chi tiết” cho môi trường Java 17+:** từ Java 15 trở đi, HotSpot đã chuyển mặc định sang bật. Chỉ thêm dấu `+` khi cần cấu hình rõ ràng hoặc xác nhận môi trường cụ thể.

## 7. Giới hạn của thông tin được suy ra

Helpful NPE rất hữu ích nhưng **không phải bộ phân tích nguyên nhân tận gốc**. Một số giới hạn quan trọng:

### 7.1. Chỉ cho thấy nơi dùng `null`, không cho biết nguồn gốc

Thông báo:

```text
Cannot invoke "String.length()" because "user.profile.email" is null
```

cho biết chính **trường email** cung cấp `null` tại lúc gọi `length()`. Nó **không** biết trường bị `null` vì constructor bỏ qua dữ liệu, mapping từ JSON lỗi, database trả dữ liệu thiếu hay luồng xử lý đã sửa state. Phải điều tra luồng tạo và truyền đối tượng để tìm nguyên nhân thật.

### 7.2. Có thể không có tên biến nguồn

Nếu metadata `LocalVariableTable` không được cung cấp, bị loại khỏi `.class` hoặc chương trình được biến đổi bởi công cụ hậu xử lý, JVM có thể sử dụng tên slot như `<local0>`. Tên phương thức hoặc trường có thể bị thay đổi bởi obfuscation, làm thông điệp kém tương đồng với mã nguồn gốc.

### 7.3. Không phải mọi NPE đều do JVM tạo ở một dereference

`throw new NullPointerException("missing value")` là exception do **mã ứng dụng** tự tạo. Thông điệp `getMessage()` khi đó chủ yếu là dữ liệu do tác giả truyền. Tương tự, một thư viện có thể tự tạo NPE để báo tham số không hợp lệ; không có bảo đảm rằng JVM sẽ ghép thêm diễn giải bytecode của điểm lỗi vào thông điệp đó.

Theo Javadoc, `NullPointerException.getMessage()` có thể trả về `null` nếu không có đủ thông tin nội bộ; trường hợp NPE đã được **deserialize** cũng không còn thông tin nội bộ cần thiết để tái tạo thông điệp chi tiết.

### 7.4. JVM có thể cung cấp mức chi tiết khác nhau

Cơ chế của JEP 358 mô tả hành vi của HotSpot và các JVM có hỗ trợ tùy chọn tương ứng. **Nội dung văn bản chính xác không phải hợp đồng API ổn định** trên mọi implementation và mọi JDK. Đừng parse thông điệp bằng regex như một API nghiệp vụ hay dựa vào một chuỗi tiếng Anh cố định để quyết định logic.

### 7.5. Vấn đề bảo mật và dữ liệu nhạy cảm

Thông điệp chi tiết có thể để lộ **cấu trúc nội bộ** của đối tượng: tên trường, tên phương thức và một phần đường dẫn dữ liệu. Không hiển thị stack trace hoặc thông điệp NPE thô cho người dùng cuối trên ứng dụng công khai. Ghi log ở nơi có kiểm soát, loại bỏ dữ liệu nhạy cảm và trả lỗi chung phù hợp cho API.

**Cách xử lý lỗi tốt nhất** không phải luôn tắt thông báo chi tiết: hãy giữ chẩn đoán hữu ích trong môi trường phát triển/vận hành được kiểm soát, đồng thời có tầng xử lý ngoại lệ và logging an toàn.

## 8. Quy trình điều tra lỗi thực tế

Khi gặp `NullPointerException` có thông điệp hữu ích:

1. **Đọc phần đầu “Cannot ...”** để biết thao tác hỏng: gọi phương thức, đọc trường, mảng...
2. **Đọc phần “because ... is null”** để xác định biểu thức đưa tham chiếu `null` đến thao tác ấy.
3. **Xem stack trace** để tìm lớp, phương thức, tệp và dòng nếu metadata hỗ trợ. Nếu hiện `Unknown Source`, có thể tệp `.class` thiếu thông tin debug nguồn.
4. **Kiểm tra điểm khởi tạo/nhận dữ liệu** của biểu thức đó: constructor, mapper, DI, HTTP, database, dữ liệu từ luồng khác...
5. **Kiểm tra bytecode khi cần** bằng `javap -c -l -p` và xác nhận cấu hình `-g` của build.
6. **Sửa hợp đồng dữ liệu** thay vì chỉ che NPE: dùng kiểm tra `null` chủ động, `Objects.requireNonNull` tại ranh giới cần thiết, giá trị mặc định hợp lý hoặc thiết kế trạng thái rõ ràng.
7. **Thêm kiểm thử hồi quy** với trường hợp thiếu dữ liệu phù hợp; không yêu cầu chuỗi thông báo lỗi giống 100% giữa các JDK.

Ví dụ để báo lỗi tham số rõ nghĩa tại ranh giới của một API:

```java
import java.util.Objects;

static int emailLength(String email) {
    String checked = Objects.requireNonNull(email, "email is required");
    return checked.length();
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp Java hợp lệ. Với `email == null`, `Objects.requireNonNull` ném NPE có thông điệp tường minh `"email is required"`, giúp hợp đồng API rõ ràng. Nó khác với trường hợp JVM tự tạo thông báo bằng cách nhìn vào bytecode của thao tác `checked.length()`.

Đừng thêm các phép kiểm tra `null` tùy tiện chỉ để làm yên log. Hãy xác định rõ input nào được phép `null`, input nào vi phạm hợp đồng và input nào cần xử lý theo nhánh nghiệp vụ.

## 9. Các hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao không đúng? | Cách hiểu chính xác |
| --- | --- | --- |
| “JVM đọc tệp `.java` để biết biểu thức nào là `null`” | Chương trình thường chạy từ `.class`, có thể không mang mã nguồn | Helpful NPE phân tích **bytecode** của thao tác lỗi |
| “Không dùng `javac -g` thì NPE chỉ có dòng trống” | Bytecode vẫn giữ cấu trúc trường/phương thức và thao tác | Thường vẫn có chi tiết, nhưng tên biến có thể thành `<local0>` |
| “`<local0>` là tên biến trong nguồn” | Đó là vị trí slot JVM, không phải identifier nguồn | Tìm phương thức/bytecode hoặc biên dịch có bảng tên biến |
| “`LineNumberTable` là nơi lưu tên `nickname`” | Bảng dòng chỉ giúp ánh xạ vị trí bytecode sang dòng nguồn | Tên biến cục bộ thuộc `LocalVariableTable` |
| “`-g:none` xóa tên mọi trường/phương thức” | Class file cần thông tin symbolic cho truy cập trường/phương thức | Nó loại **metadata debug**, không bỏ nội dung mã thực thi |
| “Bật cờ JVM tương đương biên dịch với `-g`” | Một cái chỉnh runtime, một cái chỉnh `.class` | Kiểm tra hai loại cấu hình riêng |
| “Java 17 phải bật cờ chi tiết NPE vì Java 14 từng tắt” | Mặc định thay đổi từ Java 15 | Kiểm tra mặc định của JVM đang sử dụng |
| “NPE tự tạo luôn có câu ‘Cannot ... because ...’” | Có thể do lập trình viên truyền thông điệp vào constructor | Helpful NPE chủ yếu cho lỗi **do JVM tạo** |
| “Lỗi NPE nêu được nguyên nhân nghiệp vụ” | JVM chỉ biết biểu thức đưa `null` vào thao tác hiện tại | Truy lần theo nguồn dữ liệu để tìm nguyên nhân gốc |
| “Có thể parse câu NPE làm giao thức ổn định” | Cách viết thông điệp có thể thay đổi theo JVM/phiên bản | Dùng kiểu exception, cấu trúc API và kiểm thử phù hợp |
| “In thông điệp NPE ra HTTP response luôn an toàn” | Có thể lộ tên trường/đường dẫn nội bộ | Phân biệt logging nội bộ và lỗi công khai |

## 10. Bài tập tự kiểm tra

**Câu 1.** Một JVM báo `Cannot read field "email" because "user.profile" is null`. Biểu thức nào là `null`?  
**Đáp án:** `user.profile`. Thao tác đọc `email` đã thất bại; chưa thể gọi `length()` trên giá trị email.

**Câu 2.** Cùng một chương trình biên dịch với `-g` và `-g:none`. Tại sao thông báo có thể đổi từ `"nickname"` sang `"<local0>"`?  
**Đáp án:** Vì `-g` cung cấp tên biến trong `LocalVariableTable`, còn `-g:none` loại thông tin đó. JVM vẫn biết slot từ bytecode.

**Câu 3.** Không có `LocalVariableTable` thì tên trường `email` có còn xuất hiện được không?  
**Đáp án:** Có thể. Tên trường liên quan đến cấu trúc truy cập trong class file, không phụ thuộc riêng vào bảng tên biến cục bộ.

**Câu 4.** Số dòng trong stack trace lấy từ bảng nào?  
**Đáp án:** Thông thường từ `LineNumberTable`; tên file nguồn từ `SourceFile` nếu thông tin này tồn tại.

**Câu 5.** `new NullPointerException("missing value")` có nhất thiết được JVM bổ sung “Cannot invoke ...” không?  
**Đáp án:** Không. Đó là NPE do ứng dụng tạo với thông điệp tường minh; `getMessage()` trả chuỗi tác giả cung cấp.

**Câu 6.** Java 17 có cần bật cờ `-XX:+ShowCodeDetailsInExceptionMessages` để Helpful NPE hoạt động theo mặc định trên HotSpot không?  
**Đáp án:** Không. Tùy chọn được bật mặc định từ Java 15; vẫn có thể cấu hình lại bằng cờ dấu `+` hoặc `-`.

**Câu 7.** Khi message chỉ ra trường `user.profile.email` là `null`, có biết chắc nguyên nhân là truy vấn database trả thiếu email không?  
**Đáp án:** Không. Cần điều tra luồng sinh dữ liệu; JVM chỉ chỉ ra điểm dereference gây lỗi.

**Câu 8.** Có nên kiểm tra đúng toàn bộ câu NPE trong test tương thích nhiều JDK không?  
**Đáp án:** Thường không. Cú pháp thông điệp mang tính implementation-dependent; nên test hành vi nghiệp vụ, loại exception và giá trị đầu ra ổn định.

## 11. Ghi nhớ và tài liệu chuẩn

**Helpful NullPointerExceptions** tận dụng bytecode để chỉ ra **thao tác thất bại** và **biểu thức cung cấp `null`**. Metadata debug như `LocalVariableTable` nâng chất lượng thông báo bằng **tên biến nguồn**, còn `LineNumberTable`/`SourceFile` giúp stack trace thể hiện vị trí nguồn. Mất debug info **không làm biến mất khả năng phân tích bytecode**.

Trong Java 17+ dùng HotSpot, tính năng được bật theo mặc định. Khi điều tra lỗi, cần tách **vị trí `null` ở bytecode** khỏi **nguyên nhân tạo ra `null` trong dữ liệu/luồng nghiệp vụ** và lưu ý rủi ro tiết lộ cấu trúc nội bộ khi hiển thị thông báo.

**Tài liệu chính thức và còn hiệu lực:**

- [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): mục tiêu và cơ chế phân tích bytecode.
- [Oracle Java 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): ý nghĩa và mặc định của `-XX:+ShowCodeDetailsInExceptionMessages`.
- [Oracle Java 17 — `javac` compiler options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-g`, `-g:vars`, `-g:none` và debug metadata.
- [Oracle Java 17 — `NullPointerException` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): `getMessage()`, giới hạn của thông điệp chi tiết và exception đã deserialize.
- [Oracle JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): xác nhận cờ NPE chi tiết được **bật mặc định từ JDK 15**.
- [Oracle JVM Specification Java 17 `4.7.12 và `4.7.13](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): thuộc tính `LineNumberTable` và `LocalVariableTable` của class file.