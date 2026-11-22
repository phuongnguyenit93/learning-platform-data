# Phân biệt nạp, liên kết và khởi tạo lớp hoặc interface trong Java

Khi JVM sử dụng một kiểu Java, ba khái niệm **nạp (loading)**, **liên kết (linking)** và **khởi tạo (initialization)** mô tả những công việc khác nhau. Chúng có quan hệ theo trình tự, nhưng không đồng nghĩa và cũng không nhất thiết đều diễn ra ngay khi chương trình bắt đầu. Hiểu đúng sự khác nhau giúp giải thích vì sao lỗi có thể xuất hiện trước hoặc trong khối `static`, vì sao một lớp chưa chạy initializer dù đã được nạp, và vì sao một interface có phương thức mặc định đôi khi được khởi tạo khi một lớp triển khai nó.

## 1. Bức tranh tổng quát

Thông thường, vòng đời một kiểu có thể mô tả như sau:

```text
Nạp (Loading)
    ↓
Liên kết (Linking)
    ├─ Xác minh (Verification)
    ├─ Chuẩn bị (Preparation)
    └─ Phân giải tham chiếu (Resolution)
    ↓
Khởi tạo (Initialization)
```

Đây là mô hình khái quát. JVM có thể trì hoãn việc nạp một kiểu cho đến khi cần và có thể phân giải một số tham chiếu muộn hơn thời điểm liên kết ban đầu. Vì vậy, không nên suy ra rằng mọi lớp trong ứng dụng đều được nạp, liên kết và khởi tạo hết ngay lúc khởi động.

| Giai đoạn | JVM thực hiện điều gì? | Điều đó chưa có nghĩa là gì? |
|---|---|---|
| Nạp | Tìm biểu diễn nhị phân của kiểu, tạo biểu diễn kiểu trong JVM và xác định lớp nạp chịu trách nhiệm. | Chưa chạy các khối `static` hay initializer của trường thông thường. |
| Liên kết | Kiểm tra tính hợp lệ, chuẩn bị các trường `static` và phân giải các tham chiếu tượng trưng khi cần. | Chưa thực thi toàn bộ mã khởi tạo tĩnh của kiểu. |
| Khởi tạo | Thực thi các phép gán trường `static` và khối `static` theo quy tắc của Java. | Không phải là một lần nạp hay liên kết mới; mỗi lớp hoặc interface được khởi tạo tối đa một lần cho mỗi định danh lớp trong JVM. |

## 2. Nạp kiểu (Loading)

Nạp là bước JVM tìm dữ liệu nhị phân của lớp hoặc interface và tạo biểu diễn runtime tương ứng. Nguồn dữ liệu thường là tệp `.class`, nhưng cũng có thể đến từ một class loader tùy chỉnh hoặc nguồn khác được loader hỗ trợ.

Các điểm cần nhớ:

- Một **class loader** chịu trách nhiệm tìm và nạp kiểu. Cơ chế delegation thường cho phép loader hỏi loader cha trước, nhưng loader tùy chỉnh có thể có chính sách riêng.
- Sau khi nạp, JVM có thông tin về kiểu và có thể tạo đối tượng `java.lang.Class` đại diện cho kiểu đó.
- Nạp không đồng nghĩa với việc chạy các câu lệnh trong `static { ... }`. Những câu lệnh này thuộc giai đoạn khởi tạo.
- JVM có thể nạp kiểu theo nhu cầu. Việc khai báo một biến có kiểu nào đó không nhất thiết khiến toàn bộ mã của kiểu ấy được khởi tạo ngay.
- Danh tính kiểu phụ thuộc vào cả tên nhị phân lẫn class loader định nghĩa nó. Hai class loader khác nhau có thể định nghĩa hai kiểu khác nhau dù tên nhị phân giống nhau; điều này quan trọng với plugin, container và hệ thống module tự xây dựng.

Có thể yêu cầu nạp một lớp mà chưa khởi tạo bằng `Class.forName(name, false, loader)`. Ngược lại, overload `Class.forName(name)` thông thường yêu cầu khởi tạo lớp được tìm thấy. Các lời gọi reflection và class loader cần được chọn đúng theo mục đích.

## 3. Liên kết (Linking)

Liên kết làm cho kiểu đã nạp sẵn sàng được sử dụng trong runtime. Theo mô hình JVM, liên kết gồm ba phần.

### 3.1. Xác minh (Verification)

JVM kiểm tra cấu trúc và bytecode để bảo đảm kiểu tuân thủ các ràng buộc của định dạng class file và các quy tắc an toàn của máy ảo. Ví dụ, bytecode phải có cấu trúc hợp lệ và các thao tác trên ngăn xếp toán hạng phải nhất quán.

Nếu kiểu không hợp lệ, JVM có thể ném lỗi dạng `VerifyError`. Lỗi này thuộc quá trình xác minh, khác với ngoại lệ do mã bên trong khối `static` tự ném ra khi khởi tạo.

### 3.2. Chuẩn bị (Preparation)

JVM tạo các trường lớp cần thiết và thiết lập giá trị mặc định cho các biến `static`, chẳng hạn:

- `int` có giá trị mặc định `0`;
- `boolean` có giá trị mặc định `false`;
- kiểu tham chiếu có giá trị mặc định `null`.

Đây chưa phải là thời điểm thực thi các biểu thức Java như `static int count = calculate();` hoặc các khối `static`. Các biểu thức và khối đó được thực thi khi kiểu được khởi tạo. Trường hằng biên dịch được khai báo bằng `static final` với biểu thức hằng có quy tắc riêng của JVM; không nên dùng chúng để quan sát thời điểm khởi tạo, vì giá trị hằng có thể được nhúng trực tiếp vào mã bên gọi.

### 3.3. Phân giải tham chiếu (Resolution)

Bytecode thường chứa tham chiếu tượng trưng đến lớp, trường hoặc phương thức. Phân giải chuyển những tham chiếu đó thành các liên kết mà JVM có thể sử dụng trong runtime.

JVM có thể phân giải tham chiếu theo cách sớm hoặc trì hoãn đến khi tham chiếu được sử dụng, tùy theo quy tắc và cách triển khai. Vì thế, không nên coi việc một lớp đã nạp là bằng chứng rằng mọi tham chiếu của nó đã được phân giải hoàn toàn.

## 4. Khởi tạo (Initialization)

Khởi tạo là lúc các initializer Java thực sự chạy. Với lớp, JVM thực thi mã khởi tạo lớp, thường được trình biên dịch biểu diễn trong phương thức đặc biệt `<clinit>`. Mã này bao gồm các phép gán trường `static` và khối `static`, theo thứ tự văn bản xuất hiện trong phần khai báo của lớp.

Ví dụ:

```java
class Example {
    static int first = printAndReturn("first", 1);

    static {
        System.out.println("static block");
    }

    static int second = printAndReturn("second", 2);

    private static int printAndReturn(String name, int value) {
        System.out.println(name);
        return value;
    }
}
```

Khi `Example` được khởi tạo lần đầu, các initializer tĩnh được chạy theo thứ tự trong mã nguồn: in `first`, in `static block`, rồi in `second`. Việc JVM đã nạp hoặc chuẩn bị lớp từ trước không làm thay đổi thứ tự đó.

### 4.1. Những thao tác thường kích hoạt khởi tạo lớp

Theo quy tắc ngôn ngữ Java, khởi tạo lớp thường được kích hoạt trước các thao tác sử dụng chủ động như:

- Tạo một thể hiện bằng `new`.
- Gọi một phương thức `static` được khai báo bởi lớp đó.
- Đọc hoặc ghi một trường `static` không phải biến hằng biên dịch được khai báo bởi lớp đó.
- Một số thao tác reflection yêu cầu khởi tạo, chẳng hạn `Class.forName(name)` với overload mặc định.

Việc chỉ tham chiếu đến kiểu ở những ngữ cảnh không yêu cầu khởi tạo không nhất thiết kích hoạt các initializer tĩnh. Đặc biệt, đọc một biến hằng biên dịch được như `static final int LIMIT = 10;` thường không kích hoạt khởi tạo lớp khai báo hằng, vì trình biên dịch có thể nhúng giá trị `10` vào mã bên gọi.

Một lưu ý khác: nếu gọi phương thức `static` thông qua tên một lớp con nhưng phương thức thực sự được khai báo ở lớp cha, lớp được khởi tạo theo quy tắc của lớp khai báo phương thức. Không nên chỉ nhìn tên đứng trước dấu chấm để kết luận lớp nào sẽ được khởi tạo.

### 4.2. Thứ tự khởi tạo giữa lớp cha, interface và lớp con

Khi một lớp được khởi tạo:

1. Lớp cha của nó được khởi tạo trước.
2. Các superinterface của lớp có khai báo phương thức `default` được khởi tạo theo thứ tự quy định, bao gồm quá trình duyệt các superinterface liên quan.
3. Sau đó các initializer tĩnh của chính lớp được thực thi theo thứ tự văn bản.

Quy tắc với interface có một điểm khác biệt: **khởi tạo một interface không tự động có nghĩa là khởi tạo tất cả superinterface của nó**. Nhưng khi khởi tạo một lớp, JVM sẽ khởi tạo những superinterface liên quan có khai báo phương thức mặc định theo quy tắc trên. Vì vậy, một interface có phương thức `default` có thể được khởi tạo ngay trước lớp triển khai nó, ngay cả khi chương trình chưa gọi phương thức mặc định đó.

## 5. Thử phân biệt nạp kiểu và khởi tạo (Java 17+)

Ví dụ này tập trung vào ranh giới giữa **biết kiểu đã được nạp** và **thực thi static initializer**. Ta chủ động yêu cầu JVM tìm kiểu với cờ không khởi tạo, rồi mới kích hoạt initialization trong một thao tác riêng. Lưu vào tệp `InitializationPhasesDemo.java`.

~~~java
public class InitializationPhasesDemo {
    static class Target {
        static int value = initialize();

        private static int initialize() {
            System.out.println("Target: initialized");
            return 42;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("main: before load");

        Class<?> target = Class.forName(
                "InitializationPhasesDemo$Target",
                false,
                InitializationPhasesDemo.class.getClassLoader());
        System.out.println("loaded: " + target.getSimpleName());

        System.out.println("main: before active initialization");
        Class.forName(target.getName(), true, target.getClassLoader());
        System.out.println("Target.value = " + Target.value);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InitializationPhasesDemo.java
java InitializationPhasesDemo
~~~

Stdout của ví dụ:

~~~text
main: before load
loaded: Target
main: before active initialization
Target: initialized
Target.value = 42
~~~

`Class.forName(name, false, loader)` yêu cầu tìm và nạp kiểu nhưng không yêu cầu thực thi initializer. Vì vậy, thông báo `loaded: Target` xuất hiện mà chưa có `Target: initialized`. Đối số `true` ở lời gọi thứ hai yêu cầu khởi tạo kiểu: lúc đó hàm `initialize()` chạy và gán `value = 42`. Lần đọc `Target.value` sau cùng sử dụng giá trị có sẵn, không chạy lại initializer.

Ví dụ **không đo trực tiếp linking**. JVM có thể thực hiện verification, preparation và một phần resolution ở những thời điểm khác nhau mà không in dấu vết từ mã Java. Để phân biệt loading và linking trong chẩn đoán thực tế, cần kết hợp đặc tả JVM với công cụ chẩn đoán phù hợp; riêng thứ tự `println` chỉ chứng minh lúc initializer thực thi.

Quy tắc lớp cha và superinterface có khai báo `default method` khi khởi tạo lớp được khảo sát chuyên sâu ở bài về khởi tạo lớp và interface cha. Đây là hành vi xảy ra **trước initializer của lớp**, không thay đổi ba giai đoạn loading, linking và initialization đang được phân biệt.

## 6. Điều gì xảy ra nếu khởi tạo thất bại?

Nếu mã khởi tạo tĩnh ném một ngoại lệ không phải `Error`, JVM thường biểu diễn lỗi khởi tạo lần đầu bằng `ExceptionInInitializerError`. Nếu chính lỗi là một `Error`, lỗi đó có thể được truyền trực tiếp. Lớp được đánh dấu là khởi tạo thất bại; các lần sử dụng tiếp theo thường gặp `NoClassDefFoundError` thay vì chạy lại initializer như thể chưa có gì xảy ra.

Điều này giải thích vì sao lỗi có thể xuất hiện ở lần đầu một lớp được sử dụng, dù chương trình đã biên dịch thành công và lớp đã được nạp. Biên dịch, xác minh bytecode và chạy initializer là những bước khác nhau, nên thành công ở một bước không bảo đảm thành công ở các bước sau.

## 7. Lỗi hiểu thường gặp và cách kiểm tra

- **Nhầm nạp với khởi tạo:** một lớp có thể đã được nạp nhưng khối `static` chưa chạy. Dùng `Class.forName(name, false, loader)` khi cần yêu cầu nạp mà không yêu cầu khởi tạo.
- **Cho rằng mọi lớp được khởi tạo lúc ứng dụng bắt đầu:** JVM có thể trì hoãn nạp và khởi tạo cho đến khi kiểu được sử dụng theo cách cần thiết.
- **Coi linking là một thao tác duy nhất:** verification, preparation và resolution có mục đích khác nhau; resolution còn có thể được trì hoãn.
- **Cho rằng interface và lớp có thứ tự giống hệt nhau:** khởi tạo interface không tự động khởi tạo tất cả superinterface; còn khi khởi tạo lớp, các superinterface khai báo phương thức `default` được xử lý theo quy tắc riêng.
- **Dùng hằng `static final` để thử thời điểm khởi tạo:** biến hằng biên dịch được có thể được nhúng vào mã gọi, nên đọc nó không phải phép thử đáng tin cậy.
- **Cho rằng lỗi initializer sẽ được thử lại mỗi lần:** sau khi khởi tạo thất bại, JVM ghi nhận trạng thái lỗi của kiểu; các lần dùng sau có thể ném lỗi khác như `NoClassDefFoundError`.

Khi chẩn đoán, hãy xác định thao tác nào đầu tiên yêu cầu khởi tạo kiểu, kiểm tra lớp cha và các interface có phương thức mặc định, rồi đọc các phép gán `static` và khối `static` theo thứ tự mã nguồn. Tách riêng lỗi định dạng/bytecode, lỗi liên kết và lỗi trong initializer giúp khoanh vùng nguyên nhân nhanh hơn.

## 8. Ghi nhớ

- **Loading:** tìm và tạo biểu diễn runtime của kiểu.
- **Linking:** xác minh kiểu, chuẩn bị các trường và phân giải tham chiếu khi cần.
- **Initialization:** chạy các initializer tĩnh theo thứ tự do Java quy định.
- Lớp cha được khởi tạo trước lớp con; superinterface khai báo phương thức `default` có quy tắc khởi tạo đặc biệt khi một lớp được khởi tạo.
- Mỗi lớp hoặc interface được khởi tạo tối đa một lần cho mỗi định danh kiểu trong JVM. Việc nạp và liên kết có thể diễn ra trước đó và không đồng nghĩa với khởi tạo.
