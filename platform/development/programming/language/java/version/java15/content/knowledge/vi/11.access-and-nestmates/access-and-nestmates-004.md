# Phân biệt quyền Lookup với quyền của mã được sinh (Java 15+)

## Mục tiêu

Trong Java, **MethodHandles.Lookup** là một đối tượng mang khả năng truy cập khi tìm phương thức, trường hoặc **định nghĩa hidden class**. Ngược lại, **bytecode của lớp được sinh** được JVM kiểm tra quyền theo **danh tính lớp thực thi, package, module và quan hệ nest**, không tự nhận mọi quyền từ đối tượng Lookup từng tạo ra lớp. Bài học giúp:

- Phân biệt **quyền để định nghĩa lớp** và **quyền của lệnh bytecode khi lớp chạy**.
- Hiểu điều kiện **full privilege access** của **Lookup.defineHiddenClass(...)**.
- Hiểu **ClassOption.NESTMATE** và vì sao nó thay đổi khả năng truy cập **private** trong cùng nest.
- Phân biệt **IllegalAccessException** của một thao tác Lookup với **IllegalAccessError** của bytecode lúc liên kết/thực thi.
- Xác minh bằng một chương trình Java 17+ có thể biên dịch và chạy độc lập.

Các API trong bài chính thức có từ Java 15 hoặc sớm hơn và vẫn được hỗ trợ trong Java 17 trở lên.

## 1. Hai lớp quyền khác nhau

Hãy tách bài toán thành **hai thời điểm**, với **hai chủ thể**:

**Thời điểm A — framework định nghĩa một lớp:**

~~~java
MethodHandles.Lookup ownerLookup = MethodHandles.lookup();
MethodHandles.Lookup hiddenLookup =
        ownerLookup.defineHiddenClass(classBytes, true);
Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Đây là **đoạn minh họa**, không phải file Java độc lập. Biến classBytes phải chứa bytecode lớp hợp lệ, cùng package với lookup class; lời gọi có thể cần xử lý IllegalAccessException và các lỗi định dạng/liên kết. Ở thời điểm này, JVM kiểm tra **quyền của ownerLookup** để quyết định có được dùng API định nghĩa hidden class hay không.

**Thời điểm B — mã trong hidden class thực hiện truy cập một thành viên:**

~~~java
// Nội dung của một lớp mẫu dùng làm bytecode cho hidden class.
public static int readSecret() {
    return HiddenAccessDemo.secret;
}
~~~

Lệnh truy cập trường **HiddenAccessDemo.secret** được JVM kiểm tra theo **quan hệ truy cập của lớp thực thi** (hidden class) với lớp khai báo trường. Việc ownerLookup có thể truy cập secret **không đồng nghĩa** mã của hidden class được phép truy cập trường đó.

**Nguyên tắc cốt lõi:** Lookup là **năng lực của một đối tượng được cấp phép**; quyền truy cập của bytecode là **quy tắc JVM áp dụng cho lớp đang thực thi**. Chúng có liên quan khi bạn cấu hình định nghĩa lớp, nhưng **không phải cùng một loại quyền**.

## 2. Lookup mang quyền gì?

Đối tượng **MethodHandles.Lookup** có **lookup class** và một tập các **lookup mode** giới hạn khả năng tìm và tạo method handle. API hiện hành có các mode như **PUBLIC, PRIVATE, PROTECTED, PACKAGE, MODULE, ORIGINAL** và **UNCONDITIONAL**. Tập mode cụ thể tùy cách Lookup được tạo và chuyển giao.

Các cách lấy Lookup thường gặp:

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
MethodHandles.Lookup weaker = caller.dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

Đây là **đoạn minh họa bên trong một phương thức Java** đã import MethodHandles. Cả ba đối tượng không có cùng quyền:

- **MethodHandles.lookup()** tạo Lookup theo ngữ cảnh lớp thực hiện lời gọi. Khi được gọi trực tiếp từ lớp chủ, Lookup có quyền thích hợp để tạo method handle tới những thành viên mà mã lớp chủ được phép truy cập, kể cả private của chính lớp đó; thường có **full privilege access**.
- **MethodHandles.publicLookup()** có quyền công khai bị giới hạn, không có quyền truy cập private/package/module của lớp chủ tương tự Lookup ở trên.
- **dropLookupMode(...)** chủ động bỏ bớt quyền; thao tác hạ quyền này không thể phục hồi quyền đã bị bỏ chỉ bằng cách sử dụng lại đối tượng Lookup yếu hơn.
- **lookup.in(SomeClass.class)** có thể đổi lookup class nhưng không tự nâng quyền. Quyền có thể bị mất khi đổi lớp, package hoặc module.
- **MethodHandles.privateLookupIn(...)** là API xin Lookup trong ngữ cảnh lớp đích với điều kiện quyền/module thích hợp; không phải cách tự động vượt quyền truy cập của mọi module.

**Lookup là capability:** nếu đưa một Lookup có quyền cao cho thành phần không tin cậy, thành phần đó có thể lợi dụng các API mà Lookup cho phép. Không nên truyền một Lookup đầy đủ quyền ra ngoài chỉ vì lớp nhận là hidden class.

### Full privilege access khi định nghĩa hidden class

Để gọi **Lookup.defineHiddenClass(byte[], boolean, ClassOption...)**, Lookup phải có **full privilege access** theo hợp đồng API; có thể kiểm tra bằng **hasFullPrivilegeAccess()**. Nếu thiếu quyền, API có thể ném **IllegalAccessException**.

Điều kiện này chỉ cho phép **định nghĩa một lớp theo quy tắc API**. Nó **không cấp đặc quyền tự động cho tất cả bytecode bên trong lớp mới**.

Ngoài full privilege, class-file bytes phải hợp lệ và khai báo lớp thuộc **cùng package** với lookup class. Điều kiện package liên quan đến nơi JVM định nghĩa lớp, không tự chứng minh bytecode được quyền đọc trường private của một lớp khác.

## 3. Quyền truy cập của bytecode được quyết định thế nào?

Khi bytecode thực hiện truy cập như **getstatic, putfield, invokevirtual, invokestatic**, JVM kiểm tra quy tắc truy cập tương ứng với **lớp khai báo thành viên** và **lớp thực hiện tham chiếu**.

Các yếu tố quan trọng:

| Thành viên được truy cập | Điều kiện khái quát |
| --- | --- |
| **public** | Phải thỏa quyền truy cập tới lớp/chủ thể, bao gồm quy tắc module liên quan. |
| **package-private** (không có modifier) | Cần thuộc **cùng runtime package** với lớp khai báo. |
| **protected** | Theo quy tắc package hoặc kế thừa/protected của Java và JVM. |
| **private** | Chỉ lớp khai báo hoặc **các lớp cùng nest hợp lệ** được truy cập trực tiếp. |

**Runtime package** không chỉ là một chuỗi tên package giống nhau: nó còn gắn với việc lớp được định nghĩa bởi **class loader** thích hợp. Vì vậy, hai lớp trông như cùng package trong mã nguồn không nhất thiết có quyền package-private như nhau nếu nằm trong các runtime package khác nhau.

Đặc biệt, quyền private dựa vào **nest**: các lớp thuộc cùng một nest có thể truy cập private của nhau theo quy tắc nestmate. Điều này là **quyền của các lớp**, không phải tài sản chung tự động của mọi bytecode do một Lookup có quyền cao sinh ra.

Nếu JVM từ chối truy cập thành viên khi liên kết hoặc thực thi mã đã sinh, **IllegalAccessError** có thể phát sinh. Nó là một loại **LinkageError**, khác với **IllegalAccessException** được một API Lookup ném khi lời gọi cấp quyền của chính API thất bại.

## 4. Hidden class mặc định KHÔNG tự tham gia nest của lookup class

Giả sử có lớp chủ **HiddenAccessDemo**, với trường:

~~~java
private static int secret = 42;
~~~

Một nested class trong Java source có thể truy cập trường private của lớp chủ vì chúng được biên dịch với quan hệ nestmate thích hợp:

~~~java
public static class Template {
    public static int readSecret() {
        return HiddenAccessDemo.secret;
    }
}
~~~

Nhưng khi lấy bytecode của **Template.class** làm đầu vào cho **defineHiddenClass(bytes, true)**, JVM định nghĩa **một hidden class mới**, không tái sử dụng chính Class object của Template.

**Mặc định, hidden class có nest riêng gồm chính nó**, kể cả khi class file mẫu có thông tin NestHost do compiler tạo. Quan hệ nest của hidden class được JVM xác định theo **ClassOption.NESTMATE** lúc định nghĩa; **không tự lấy quan hệ nest từ NestHost attribute trong file bytes**.

Hệ quả quan trọng:

- Lookup của lớp chủ **được phép** định nghĩa hidden class.
- Hidden class mới **được tạo thành công** và có Class object hợp lệ.
- Nhưng nếu bytecode đó truy cập trực tiếp private của lớp chủ, JVM có thể ném **IllegalAccessError** vì hidden class **không phải nestmate** của lớp chủ.

Đây là ví dụ điển hình cho sự khác biệt giữa **“có quyền tạo”** và **“mã tạo ra được quyền truy cập”**.

## 5. NESTMATE thay đổi quyền ở cấp lớp, không phải chuyển giao mọi quyền Lookup

Để hidden class tham gia nest của lớp đang thực hiện Lookup, sử dụng:

~~~java
MethodHandles.Lookup hiddenLookup = ownerLookup.defineHiddenClass(
        classBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

Đây cũng là **đoạn code minh họa** với ownerLookup/classBytes đã được định nghĩa và xử lý ngoại lệ phù hợp.

**NESTMATE** yêu cầu JVM thêm hidden class vào **nest của lookup class**. Khi ấy, hidden class có thể truy cập trực tiếp **private** của các lớp trong cùng nest theo quy tắc JVM.

Không nên hiểu NESTMATE như một lệnh “bỏ hết kiểm tra quyền”:

- Nó **không** cho hidden class đọc private của **mọi** lớp bất kỳ trong chương trình.
- Các hạn chế về **module, runtime package, loại thành viên và bytecode hợp lệ** vẫn tồn tại.
- Nó **không** thay đổi quyền của một Lookup đã bị giới hạn.
- Nó **không** cấp quyền cho bytecode bên ngoài nest chỉ vì nó được framework sinh ra.
- Tham số **initialize** điều khiển khởi tạo lớp; **không** phải nút bật/tắt kiểm tra quyền.

### Vì sao NESTMATE khác với truyền MethodHandle?

Giả sử framework đã tìm được một MethodHandle tới phương thức private bằng Lookup hợp lệ. Framework có thể **chủ động chuyển** MethodHandle đó đến một thành phần được tin cậy, để thành phần gọi theo capability mà nó được trao. Đây là **hành động chuyển giao đối tượng mang quyền**, khác với việc một class tự được phép phát ra lệnh bytecode truy cập private.

Tương tự, nếu framework đưa hẳn một **Lookup có quyền cao** cho mã được sinh, mã đó có thể sử dụng những quyền mà đối tượng được trao cho phép. Nhưng việc **chỉ dùng** Lookup để gọi defineHiddenClass **không tự chuyển** toàn bộ quyền Lookup đó vào thân bytecode.

## 6. Lookup trả về trên hidden class có ý nghĩa gì?

**defineHiddenClass** trả về **MethodHandles.Lookup mới trên chính hidden class**. Trong API hiện hành, Lookup trả về có **full privilege access** trong ngữ cảnh hidden class được tạo. Điều này giúp framework tìm method/field/constructor của lớp mới hoặc tạo MethodHandle theo các quy tắc truy cập tương ứng.

~~~java
MethodHandles.Lookup newLookup =
        ownerLookup.defineHiddenClass(classBytes, true);
Class<?> generatedClass = newLookup.lookupClass();
~~~

Hai câu lệnh minh họa nói trên cho thấy **newLookup.lookupClass() là hidden class**. Nó **không** có nghĩa bytecode của hidden class được mặc nhiên xem là một thành viên của nest lớp chủ.

Phân biệt ba thứ:

1. **ownerLookup:** đối tượng có quyền của lớp chủ, dùng để định nghĩa hidden class.
2. **newLookup:** đối tượng mới dùng để tạo method handles theo ngữ cảnh **hidden class**.
3. **bytecode trong hidden class:** thực thi theo quyền **lớp thực thi và nest thực tế** khi JVM kiểm tra các tham chiếu của mã.

Nếu không chọn NESTMATE, newLookup vẫn có thể có quyền đầy đủ **trên hidden class**, nhưng lệnh bytecode truy cập private lớp chủ **vẫn có thể thất bại**.

## 7. Ví dụ Java 17+ hoàn chỉnh: đủ quyền tạo nhưng chưa đủ quyền chạy

Chương trình sau cố tình thiết kế trường private **không phải compile-time constant**, tránh compiler thay giá trị ngay trong bytecode. Lớp mẫu Template được javac biên dịch là nested class của lớp chủ, có phương thức truy cập private. Ví dụ lấy class-file bytes hợp lệ từ classpath rồi lần lượt định nghĩa hidden class **không có NESTMATE** và **có NESTMATE**.

Lưu toàn bộ mã sau vào tệp **HiddenAccessDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;

public class HiddenAccessDemo {
    private static int secret = 42;

    private static int secretFromHost() {
        return secret;
    }

    public static class Template {
        public static int readSecret() {
            return HiddenAccessDemo.secret;
        }
    }

    private static byte[] templateBytes() throws IOException {
        try (InputStream in = HiddenAccessDemo.class
                .getResourceAsStream("HiddenAccessDemo$Template.class")) {
            if (in == null) {
                throw new IOException("Thiếu Template.class");
            }
            return in.readAllBytes();
        }
    }

    private static int invokeReadSecret(Class<?> type) throws Exception {
        try {
            return (int) type.getMethod("readSecret").invoke(null);
        } catch (InvocationTargetException e) {
            if (e.getCause() instanceof IllegalAccessError) {
                System.out.println("Mã sinh không thuộc nest: IllegalAccessError");
                return -1;
            }
            throw e;
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = templateBytes();
        MethodHandles.Lookup owner = MethodHandles.lookup();
        System.out.println("Lookup gốc có full privilege: "
                + owner.hasFullPrivilegeAccess());
        System.out.println("Lookup truy cập private: "
                + (int) owner.findStatic(HiddenAccessDemo.class, "secretFromHost",
                        MethodType.methodType(int.class)).invokeExact());

        try {
            MethodHandles.publicLookup().defineHiddenClass(bytes, false);
        } catch (IllegalAccessException e) {
            System.out.println("publicLookup tạo hidden: IllegalAccessException");
        }

        Class<?> ordinaryHidden =
                owner.defineHiddenClass(bytes, true).lookupClass();
        System.out.println("Hidden mặc định cùng nest: "
                + ordinaryHidden.isNestmateOf(HiddenAccessDemo.class));
        invokeReadSecret(ordinaryHidden);

        MethodHandles.Lookup nestmateLookup = owner.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> nestmate = nestmateLookup.lookupClass();
        System.out.println("Hidden NESTMATE cùng nest: "
                + nestmate.isNestmateOf(HiddenAccessDemo.class));
        System.out.println("Mã sinh thuộc nest đọc private: "
                + invokeReadSecret(nestmate));
        System.out.println("Lookup trả về thuộc hidden: "
                + (nestmateLookup.lookupClass() == nestmate));
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 HiddenAccessDemo.java
java HiddenAccessDemo
~~~

**Stdout chính xác**, đã biên dịch với --release 17 và thực thi thành công trên JDK 24:

~~~text
Lookup gốc có full privilege: true
Lookup truy cập private: 42
publicLookup tạo hidden: IllegalAccessException
Hidden mặc định cùng nest: false
Mã sinh không thuộc nest: IllegalAccessError
Hidden NESTMATE cùng nest: true
Mã sinh thuộc nest đọc private: 42
Lookup trả về thuộc hidden: true
~~~

**Diễn giải từng bước:**

1. **Lookup gốc:** tạo từ chính HiddenAccessDemo nên có full privilege. MethodHandle tới **secretFromHost()** private hoạt động và trả 42. Đây là quyền của Lookup đang được sử dụng để tìm/gọi method handle.
2. **publicLookup:** không có full privilege, nên **defineHiddenClass(...)** thất bại với **IllegalAccessException**. Lỗi phát sinh tại bước **định nghĩa**, chưa có mã hidden class nào chạy.
3. **Hidden mặc định:** chủ Lookup đủ quyền để định nghĩa; **ordinaryHidden** tạo thành công nhưng **không cùng nest** với HiddenAccessDemo. Khi phương thức **readSecret()** cố truy cập private của lớp chủ, JVM ném **IllegalAccessError**.
4. **Lời gọi reflection:** Method.invoke(...) bọc lỗi bên trong **InvocationTargetException**; ví dụ lấy **getCause()** để nhận diện chính **IllegalAccessError** từ bytecode. Không nên nhầm wrapper reflection với loại lỗi gốc.
5. **Hidden NESTMATE:** lần định nghĩa thứ hai chỉ khác **ClassOption.NESTMATE**. JVM đặt hidden class vào nest của lớp chủ, nên cùng bytecode **readSecret()** giờ truy cập private hợp lệ và trả **42**.
6. **Lookup trả về:** **nestmateLookup.lookupClass()** chính là hidden class vừa tạo, không phải lớp chủ và không phải Template.class.

Hai hidden class trong chương trình được định nghĩa từ **cùng mảng bytes** nhưng là **hai lớp runtime khác nhau**, có **quan hệ nest khác nhau** và vì vậy **quyền thực thi khác nhau**. Bytecode không tự thay đổi.

Để tránh nhầm lẫn, trong hàm **invokeReadSecret(...)**, giá trị **-1** chỉ là **giá trị giả bên trong ví dụ sau khi đã in lỗi**, không phải kết quả Math hoặc giá trị JVM trả về từ lệnh đọc trường private bị từ chối.

## 8. Phân biệt các loại lỗi truy cập

| Tình huống | Kết quả điển hình | Cần sửa ở đâu? |
| --- | --- | --- |
| Gọi **defineHiddenClass** bằng Lookup không có full privilege | **IllegalAccessException** | Cách lấy và cấp quyền Lookup |
| Class-file bytes khai báo package không trùng với lookup class | **IllegalArgumentException** | Nguồn và package của bytecode hoặc Lookup tương ứng |
| Hidden class không phải nestmate nhưng bytecode trực tiếp truy cập private lớp chủ | **IllegalAccessError** | Quan hệ nest hoặc thiết kế truy cập trong bytecode |
| Reflection **Method.invoke** gọi phương thức ném lỗi khi đang chạy | **InvocationTargetException** bao bọc nguyên nhân | Phân tích **getCause()**, không kết luận chỉ từ wrapper |
| Lookup yếu cố tạo MethodHandle tới member mà nó không được phép truy cập | Thường **IllegalAccessException** từ API tìm member | Lookup class, lookup modes, module và member visibility |
| Lớp sinh tham chiếu tới class/member không có hoặc không phù hợp | Các lỗi liên kết khác như **NoClassDefFoundError**, **NoSuchMethodError**, **IncompatibleClassChangeError** | Phụ thuộc và classpath/module path, bytecode được sinh |

**IllegalAccessException** là checked exception của nhiều API truy cập; **IllegalAccessError** là lỗi liên kết thuộc họ **Error**. Không nên gộp chúng thành một thông báo chung rằng “không có quyền Lookup” vì nguyên nhân kỹ thuật khác nhau.

Trong chương trình sản xuất, nếu bytecode không hợp lệ hoặc thiếu quyền truy cập, nên sửa cách sinh bytecode và lựa chọn Lookup/NESTMATE. **Không bắt rồi bỏ qua LinkageError** như một cách sửa lỗi truy cập.

## 9. Khi nào dùng NESTMATE, khi nào dùng API công khai?

**Nên dùng NESTMATE** khi framework chủ động sinh một lớp hỗ trợ cần truy cập private của lớp chủ hoặc các thành viên khác trong cùng nest, có thể kiểm soát bytecode, và có quyền để định nghĩa lớp ẩn theo quy tắc JVM.

**Không cần NESTMATE** khi lớp sinh chỉ dùng các **public API**, hoặc khi có thể cung cấp dữ liệu qua tham số constructor, một interface công khai hoặc method handle được cấp có chủ đích. Thiết kế dựa vào API rõ ràng dễ đánh giá quyền hơn trong nhiều trường hợp.

**Không dùng NESTMATE để vượt module bất kỳ.** Tùy chọn này nói về **nest của lookup class**, không cho lớp sinh tham gia nest của một lớp xa lạ chỉ bằng cách đặt tên lớp đó trong bytecode.

**Không chuyển Lookup nhạy cảm cho code không tin cậy.** Một Lookup đầy đủ quyền và method handles được tạo từ nó là capability cần quản lý rõ nơi cấp phát, nơi truyền và bên nhận. **Hidden class không phải sandbox bảo mật**; JVM kiểm tra truy cập nhưng mã bytecode không tin cậy vẫn có thể gây tác động không mong muốn theo các quyền mà nó có.

## 10. Lỗi hiểu nhầm thường gặp

1. **“Lookup được đọc private, nên hidden class nào do nó tạo cũng đọc được private.”** Sai. Mặc định hidden class không cùng nest với lớp chủ. Bytecode phải qua kiểm tra truy cập riêng.
2. **“NESTMATE có nghĩa giữ nguyên NestHost trong file bytecode mẫu.”** Sai. Quyết định nest của hidden class nằm ở **ClassOption.NESTMATE** và lookup class theo API, không tự dựa vào NestHost attribute gốc của file mẫu.
3. **“HiddenLookup trả về toàn quyền trên lớp chủ.”** Sai. Lookup trả về có ngữ cảnh **hidden class**. Nó có full privilege theo ngữ cảnh đó, không tự trao quyền private trên các lớp ngoài nest.
4. **“publicLookup() đủ để định nghĩa hidden class nếu bytecode public.”** Sai. defineHiddenClass đòi **full privilege access** của Lookup, độc lập với việc lớp mẫu hay phương thức bên trong khai báo public.
5. **“IllegalAccessException và IllegalAccessError như nhau.”** Sai. Một bên xuất phát từ API truy cập, bên kia từ kiểm tra liên kết/truy cập của bytecode.
6. **“Trường private static final luôn là ví dụ tốt để thử quyền.”** Nếu đó là compile-time constant, javac có thể inline giá trị và không phát ra lệnh đọc trường lúc chạy. Hãy thử với trường private **không phải compile-time constant**, như **private static int secret = 42** trong ví dụ.
7. **“Có thể bật initialize=false để né quyền private.”** Sai. initialize điều khiển khởi tạo lớp, không cấp quyền và không xóa kiểm tra truy cập khi bytecode thật sự tham chiếu thành viên.
8. **“Chỉ cần tìm được Class object là có thể gọi private của mọi lớp.”** Sai. Có Class object không tự vượt kiểm tra truy cập của reflection, MethodHandles hay JVM.
9. **“Lookup.in(...) hay dropLookupMode(...) có thể nâng quyền đã thiếu.”** Sai. Đây là các phép có thể giới hạn quyền; chúng không tự hồi phục quyền bị loại.
10. **“Truyền một MethodHandle hoặc Lookup chỉ giống truyền tên phương thức.”** Sai. Đó có thể là **đối tượng mang quyền truy cập đã được xác thực**; cần bảo vệ và chỉ chuyển cho thành phần được tin cậy.

## 11. Tự kiểm tra

**Câu 1.** Vì sao ownerLookup tìm được phương thức private, nhưng bytecode hidden class do nó tạo lại ném IllegalAccessError?  
**Đáp án:** Quyền của ownerLookup dùng cho thao tác Lookup; bytecode hidden class được JVM kiểm tra theo class và nest thực tế. Mặc định hidden class không phải nestmate của lớp chủ.

**Câu 2.** Thêm tùy chọn gì nếu hidden class cần trực tiếp truy cập private của lookup class và các lớp cùng nest?  
**Đáp án:** **MethodHandles.Lookup.ClassOption.NESTMATE** khi gọi defineHiddenClass, nếu điều kiện Lookup/bytecode hợp lệ.

**Câu 3.** publicLookup().defineHiddenClass(...) thất bại với loại lỗi nào?  
**Đáp án:** **IllegalAccessException** vì publicLookup không có full privilege access.

**Câu 4.** Lookup trả về từ defineHiddenClass gắn với lớp nào?  
**Đáp án:** **Hidden class mới**, có thể lấy Class<?> bằng **lookupClass()**.

**Câu 5.** Làm thế nào phân biệt lỗi JVM trong mã được gọi qua Method.invoke(...) với wrapper của reflection?  
**Đáp án:** Bắt **InvocationTargetException**, kiểm tra **getCause()** để nhận diện nguyên nhân như **IllegalAccessError**.

## 12. Ghi nhớ

**Quyền Lookup quyết định Lookup được phép làm gì; quyền bytecode quyết định lớp được sinh có thể truy cập thành viên nào khi mã chạy.** Có quyền định nghĩa hidden class **không đồng nghĩa** hidden class được mặc nhiên dùng quyền private của lớp chủ. Khi thực sự cần cùng nest, hãy dùng **ClassOption.NESTMATE** một cách có chủ đích, kiểm thử bằng **Class.isNestmateOf()** và hành vi chạy thật, đồng thời tránh chuyển giao capability nhạy cảm không kiểm soát.

## Tài liệu tham khảo chính thức

- Oracle, **MethodHandles.Lookup**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle, **MethodHandles.Lookup.ClassOption.NESTMATE**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- Oracle, **MethodHandles.lookup()**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html
- OpenJDK, **JEP 371 — Hidden Classes**: https://openjdk.org/jeps/371
