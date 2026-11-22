# Khởi tạo lớp cha và thứ tự thực hiện static initializer trong Java

Khi chương trình lần đầu sử dụng một lớp theo cách buộc JVM **khởi tạo lớp** (class initialization), Java phải thiết lập trạng thái tĩnh của lớp đó. Với quan hệ kế thừa, **lớp cha được khởi tạo trước khi chạy các bộ khởi tạo tĩnh thông thường của lớp con**. Bên trong từng lớp, các lệnh gán cho trường `static` và các khối `static { ... }` được thực thi theo thứ tự xuất hiện trong mã nguồn.

Đây là quy tắc quan trọng khi đọc log khởi động ứng dụng, phân tích thứ tự đăng ký thành phần tĩnh hoặc tìm lỗi xảy ra trong `static initializer`. Tuy nhiên, có những ngoại lệ cần hiểu rõ: việc nạp lớp không nhất thiết khởi tạo lớp, đọc hằng số tại thời điểm biên dịch có thể không kích hoạt khởi tạo, truy cập thành viên `static` **kế thừa** thường khởi tạo lớp **khai báo** thành viên, và một số **superinterface có default method** cũng có thể được khởi tạo trước lớp triển khai.

## 1. Khởi tạo lớp khác gì nạp lớp và tạo đối tượng?

Ba khái niệm dễ bị trộn lẫn:

| Hoạt động | Điều xảy ra | Có bắt buộc chạy `static initializer` không? |
| --- | --- | --- |
| **Loading** | Class loader/JVM tạo định nghĩa `Class<?>` từ biểu diễn lớp. | Không nhất thiết. |
| **Linking / preparation** | JVM kiểm tra/liên kết và cấp phát các trường tĩnh với giá trị mặc định; một số hằng có `ConstantValue` được xử lý theo quy định riêng. | Chưa phải việc chạy toàn bộ khối `static`. |
| **Initialization** | JVM thực thi thủ tục khởi tạo lớp, gồm phần khởi tạo trường tĩnh và khối `static` cần thực thi. | Có, nếu lớp có các thao tác đó. |
| **Object construction** | Tạo đối tượng, chạy quá trình khởi tạo instance và constructor trong chuỗi kế thừa. | Chỉ kích hoạt khởi tạo lớp nếu định nghĩa lớp liên quan chưa được khởi tạo. |

Ví dụ, `ClassLoader.loadClass(...)` thông thường **nạp** nhưng không yêu cầu **khởi tạo** lớp; `Class.forName(name)` dạng một tham số thông thường yêu cầu khởi tạo. Với `Class.forName(name, false, loader)`, tham số `false` cho phép lấy `Class<?>` mà chưa yêu cầu chạy `static initializer`.

Đừng nhầm `static initializer` với constructor:

- `static { ... }` và phép gán cho trường `static` thông thường chạy **một lần cho mỗi định nghĩa lớp được khởi tạo thành công**, không chạy lại khi tạo thêm object.
- Khối khởi tạo instance `{ ... }`, phép gán trường instance và constructor phục vụ **mỗi lần tạo đối tượng**.
- `Class<?>.getClassLoader()` cho biết defining loader. Hai loader định nghĩa cùng tên nhị phân có thể tạo ra hai định nghĩa lớp khác nhau, mỗi định nghĩa có trạng thái khởi tạo riêng.

## 2. Quy tắc chính: lớp cha trước, lớp con sau

Giả sử có chuỗi kế thừa:

~~~text
java.lang.Object
       │
       ▼
      Root
       │
       ▼
     Parent
       │
       ▼
      Child
~~~

Khi một hành động buộc `Child` được khởi tạo và các lớp cha chưa khởi tạo, thứ tự khái quát là:

~~~text
Khởi tạo Root (sau Object nếu cần)
      ↓
Khởi tạo Parent
      ↓
Khởi tạo Child
      ↓
Tiếp tục hành động đã yêu cầu Child
~~~

Nói chính xác hơn, JVM thực hiện **thủ tục khởi tạo** đối với lớp cần dùng, rồi bảo đảm các lớp cha cần thiết và những superinterface thuộc trường hợp quy định được khởi tạo trước khi chạy phần khởi tạo thông thường của lớp hiện tại. Mỗi lớp cha đã khởi tạo thì được bỏ qua; JVM không chạy lại khối `static` của nó.

Quy tắc này bảo đảm các thành viên tĩnh và giả định khởi tạo cần thiết ở lớp cha đã sẵn sàng khi lớp con thực thi bộ khởi tạo của mình. **Không có quy tắc “khởi tạo toàn bộ lớp con khi cha được dùng”.** Chỉ dùng thành viên khai báo bởi `Parent` thường không buộc `Child` khởi tạo.

Để tránh diễn giải sai, cần phân biệt một chi tiết ở mức đặc tả: giá trị của **constant variable** có thể được thiết lập từ thuộc tính `ConstantValue` theo bước riêng của thủ tục khởi tạo; quy tắc “cha trước con” ở đây nói về **thứ tự thực thi các phép gán tĩnh thông thường và khối `static` có side effect**, không có nghĩa mọi byte dữ liệu tĩnh của lớp con đều chưa thể mang giá trị trước khi cha hoàn tất.

## 3. Trong từng lớp, trường static và khối static chạy theo thứ tự văn bản

Trong một lớp, các trình khởi tạo của trường tĩnh và khối `static` được chạy **từ trên xuống dưới**, giống như được ghép thành một khối duy nhất:

~~~java
class Settings {
    static int a = calculateA();

    static {
        System.out.println("middle");
    }

    static int b = calculateB();
}
~~~

Đây là **đoạn minh họa** để nhìn thứ tự; hai method `calculateA` và `calculateB` chưa được định nghĩa nên đoạn code này **không phải tệp Java độc lập để biên dịch**. Nếu có định nghĩa các method đó, thứ tự side effect sẽ là `calculateA()` → in `middle` → `calculateB()`.

Với dữ liệu thông thường, JVM trước hết cấp phát trường `static` và đặt **giá trị mặc định** trong giai đoạn preparation (`0`, `false`, `null`, tùy kiểu). Sau đó quá trình initialization thực hiện các phép gán có code và khối `static` theo thứ tự. Vì vậy, một initializer có thể quan sát giá trị mặc định của trường khác trong một số trường hợp phụ thuộc vòng; không được suy rằng giá trị khai báo cuối cùng đã hiện diện ở mọi thời điểm.

Các quy tắc **illegal forward reference** hạn chế một số cách dùng trường tĩnh được khai báo phía sau ngay trong initializer của cùng lớp. Nhưng phụ thuộc gián tiếp qua method hoặc qua lớp khác vẫn có thể tạo vòng khởi tạo hợp lệ về cú pháp mà khó dự đoán ở runtime.

### Khối static khác constructor ở điểm nào?

`static { ... }` được gắn với **lớp**, không phụ thuộc object cụ thể và không trực tiếp truy cập `this` hoặc `super`. Constructor được thực thi khi xây dựng **instance**, sau khi các lớp cần thiết đã khởi tạo. Nếu `new Child()` là hành động đầu tiên sử dụng `Child`, **static initialization diễn ra trước** chuỗi constructor/instance initialization.

## 4. Ví dụ Java 17: quan sát đầy đủ thứ tự Root → Parent → Child

Tạo tệp **`StaticOrderDemo.java`** với toàn bộ nội dung:

~~~java
public class StaticOrderDemo {
    private static int mark(String label, int result) {
        System.out.println(label);
        return result;
    }

    static class Root {
        static int rootValue = mark("Root.field", 1);

        static {
            System.out.println("Root.block");
        }
    }

    static class Parent extends Root {
        static {
            System.out.println("Parent.block-1");
        }

        static int parentValue = mark("Parent.field", 2);

        static {
            System.out.println("Parent.block-2");
        }
    }

    static class Child extends Parent {
        static int childValue = mark("Child.field", 3);

        static {
            System.out.println("Child.block");
        }
    }

    public static void main(String[] args) {
        System.out.println("Before Child");
        System.out.println("Value = " + Child.childValue);
        System.out.println("Again = " + Child.childValue);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 StaticOrderDemo.java
java StaticOrderDemo
~~~

**Stdout chính xác:**

~~~text
Before Child
Root.field
Root.block
Parent.block-1
Parent.field
Parent.block-2
Child.field
Child.block
Value = 3
Again = 3
~~~

**Giải thích từng bước:**

1. JVM khởi tạo `StaticOrderDemo` để chạy `main`; ba lớp lồng `Root`, `Parent`, `Child` **không phải tự động khởi tạo cùng outer class**.
2. `Before Child` xuất hiện trước khi `Child` được dùng theo cách đòi hỏi initialization.
3. Đọc `Child.childValue` buộc khởi tạo `Child`. Vì `Child` kế thừa `Parent`, còn `Parent` kế thừa `Root`, JVM thực thi các bộ khởi tạo của `Root` rồi `Parent` rồi `Child`.
4. Bên trong `Parent`, `Parent.block-1` chạy **trước** initializer `parentValue`, sau đó tới `Parent.block-2`; khối `static` không có ưu tiên tuyệt đối hơn phép gán `static`, chúng phụ thuộc **thứ tự văn bản**.
5. Sau khi các lớp được khởi tạo, biểu thức đọc field trả `3`. Đọc lại `Child.childValue` không tái chạy bất cứ block nào.

Thử thay thứ tự khai báo hai khối `static` và `parentValue` trong `Parent` rồi biên dịch lại để thấy log thay đổi theo văn bản. Đây là sự thay đổi thứ tự thực thi code trong **cùng một lớp**, còn thứ tự **cha → con** vẫn được bảo đảm.

## 5. Tên lớp trước dấu chấm chưa chắc là declaring class

Nếu `Parent` khai báo `static int shared` còn `Child extends Parent`, biểu thức `Child.shared` chỉ khởi tạo **Parent** nếu cần. Nếu `Child` khai báo field riêng cùng tên thì đó là **field hiding**, hai field tách biệt. Với `static final int LIMIT = 99` là constant variable, phép đọc hằng không tự kích hoạt initialization.

Bài **Đọc static field kế thừa: kiểu thực sự khai báo field** dạy riêng member lookup, hiding, `getDeclaringClass()` và bytecode `getstatic`. Ở bài này, điều cần giữ là **lớp thật sự sở hữu field/method** trong chuỗi init.

## 6. Static initialization và constructor theo hai lượt

Nếu `new Child()` là active use đầu, static initializer `Parent` rồi `Child` chạy trước các constructor. Sau đó chuỗi constructor `Parent()` → `Child()` chạy cho instance đó. Một object thứ hai chỉ chạy lại chuỗi constructor vì các lớp đã initialized thành công. Bài phân biệt `<clinit>`/`<init>` cung cấp ví dụ riêng về hai chuỗi.

## 7. Ngoại lệ quan trọng: superinterface có default method

Không thể diễn giải thứ tự đầy đủ chỉ bằng cây `extends`. Theo Java 17, khi một **class** được khởi tạo, JVM còn khởi tạo những **superinterface trực tiếp hoặc gián tiếp có khai báo default method** nếu chúng chưa khởi tạo. Các interface này được xét theo thứ tự đệ quy do đặc tả quy định. Ngược lại:

- Interface **không có default method** không nhất thiết được khởi tạo chỉ vì một class implements nó.
- Khởi tạo một **interface** tự nó **không kéo theo khởi tạo toàn bộ superinterface** mà nó extends.
- Những phương thức static khai báo trong interface **không phải default method**. `default` là implementation của một instance method trong interface.

Quan sát bằng ví dụ **`InterfaceInitDemo.java`**:

~~~java
public class InterfaceInitDemo {
    private static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    interface Plain {
        int NUMBER = trace("Plain initialized", 1);
    }

    interface WithDefault {
        int NUMBER = trace("WithDefault initialized", 2);

        default void run() {
            // Không cần gọi để interface được khởi tạo cùng lớp.
        }
    }

    static class Impl implements Plain, WithDefault {
        static {
            System.out.println("Impl initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("Before object");
        new Impl();
        System.out.println("After object");
        System.out.println("Plain number = " + Plain.NUMBER);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 InterfaceInitDemo.java
java InterfaceInitDemo
~~~

Stdout:

~~~text
Before object
WithDefault initialized
Impl initialized
After object
Plain initialized
Plain number = 1
~~~

`WithDefault` được khởi tạo **trước `Impl`** vì khai báo default method `run`. `Plain` chưa cần khởi tạo tại thời điểm `new Impl()`; nó chỉ khởi tạo khi truy cập `Plain.NUMBER`. Cả hai trường interface là `public static final` theo luật ngôn ngữ, nhưng initializer gọi method `trace(...)` nên **không phải compile-time constant** và quan sát được lúc initialization.

**Chi tiết nâng cao:** Với nhiều superinterface có default method, thứ tự JLS 12.4.2 dùng cách duyệt **đệ quy theo thứ tự khai báo từ trái sang phải**, xét superinterface trước interface đang duyệt, sau superclass của class; không đơn giản là “interface được viết bên trái có priority cao hơn mọi ancestor khác”. Có trường hợp trình biên dịch sinh **synthetic default method**, cũng có thể ảnh hưởng việc khởi tạo interface. Để hiểu chính xác tình huống phức tạp, đối chiếu đồ thị interface và output `javap -v` thay vì chỉ suy từ dòng `implements`.

## 8. Những hoạt động có và không yêu cầu khởi tạo lớp

Các tình huống thường gặp (giả sử lớp chưa khởi tạo, không có yếu tố khác buộc khởi tạo trước):

| Hành động | Kết quả cần nhớ |
| --- | --- |
| `new Child()` | Yêu cầu khởi tạo `Child`; lớp cha cần thiết được khởi tạo trước code static thông thường của con. |
| `Child.ownStaticField` (field khai báo ở Child, không phải constant variable) | Yêu cầu khởi tạo `Child`. |
| `Child.ownStaticMethod()` (method khai báo ở Child) | Yêu cầu khởi tạo `Child`. |
| `Child.inheritedStaticField` (field khai báo ở Parent) | Yêu cầu khởi tạo lớp **thực sự khai báo field**, không tự yêu cầu khởi tạo `Child`. |
| Đọc `static final int` được khai báo bằng constant expression | Thông thường không buộc khởi tạo lớp khai báo để đọc giá trị. |
| `Child.class` | Lấy class literal **không tự buộc** initialization. |
| `Class.forName("pkg.Child")` | Dạng thông thường yêu cầu khởi tạo `Child`. |
| `Class.forName("pkg.Child", false, loader)` | Không yêu cầu khởi tạo chỉ bởi lời gọi này. |
| `loader.loadClass("pkg.Child")` | Theo hợp đồng `loadClass` thường nạp mà không khởi tạo. |
| Tạo một instance thứ hai của `Child` | Không chạy lại `static` của `Child` đã khởi tạo thành công; constructor vẫn chạy. |

Bảng là **mô hình hành vi bắt buộc về thời điểm chạy các initializer**, không phải lịch thực tế JVM đọc tệp bytecode. JVM có thể nạp, kiểm tra hoặc resolve một lớp sớm hơn, miễn giữ đúng ngữ nghĩa quan sát được về initialization.

## 9. Khi chuỗi initialization bị gián đoạn

Nếu initializer của superclass hoặc một superinterface bắt buộc ném lỗi, lớp con không thể hoàn tất initialization bình thường. Vòng phụ thuộc do code tạo ra có thể đọc field còn mặc định; hai thread chờ chéo nhau có thể deadlock. Đó là chủ đề của ba bài riêng về **đồng bộ**, **khởi tạo đệ quy** và **initialization thất bại**. Thứ tự trong các mục trước mô tả đường thành công thông thường.

## 10. Cách suy luận và debug thứ tự initialization

Khi thấy log khác dự kiến, hãy kiểm tra theo thứ tự:

1. **Lớp nào bị “active use” trước?** Tìm `new`, `invokestatic` (gọi static method), `getstatic`/`putstatic` (field không phải constant variable), reflection hoặc điểm entry `main`.
2. **Thành viên static thực sự được khai báo ở đâu?** `Child.shared` có thể thực chất là `Parent.shared`; tránh đoán theo dấu chấm trong mã nguồn.
3. **Lớp cha nào còn chưa khởi tạo?** Lần lượt đi qua superclass chain; lưu ý các superinterface có default method của class.
4. **Trong từng lớp, thứ tự văn bản ra sao?** Đọc xen kẽ field initializer và khối `static`, không gom mọi field trước rồi mọi block sau.
5. **Có hằng compile-time không?** `static final int LIMIT = 10` có ngữ nghĩa khác `static final Integer LIMIT = 10` hoặc `static final int LIMIT = calculate()`.
6. **Có vòng phụ thuộc hoặc lỗi khởi tạo không?** Tìm exception đầu tiên, `ExceptionInInitializerError`, `NoClassDefFoundError`, hay side effect đọc giá trị mặc định.
7. **Có nhiều class loader hoặc nhiều thread không?** Cùng tên lớp nhưng khác defining loader có thể là hai định nghĩa độc lập; nhiều thread có thể chờ initialization.

Để quan sát bytecode trên HotSpot/JDK 17+, chạy:

~~~bash
javap -c -p StaticOrderDemo
javap -c -p 'StaticOrderDemo$Parent'
~~~

Lưu ý lệnh thứ hai dùng dấu nháy đơn để tránh shell diễn giải ký tự `$` trong tên lớp lồng trên các shell kiểu Unix. Trên Windows PowerShell, dấu nháy đơn cũng giữ nguyên chuỗi lớp lồng. `javap` có thể hiển thị method đặc biệt `<clinit>`, là nơi bytecode cho phép gán `static` và block `static` được gom theo thứ tự biên dịch. Dùng `javap -v -p` khi cần xem nhiều metadata hơn.

Nếu chỉ nhìn `javap -c` của từng lớp, hãy nhớ **thứ tự giữa các lớp là do thủ tục JVM initialization**, không phải do bytecode `Child.<clinit>` tự chứa toàn bộ code `Parent.<clinit>`.

## 11. Tự kiểm tra

**Câu 1.** `Child extends Parent`. Nếu `Child` chưa khởi tạo và gọi method static khai báo ở `Child`, khối `static` của ai chạy trước?

**Đáp án:** Nếu `Parent` chưa khởi tạo thì bộ khởi tạo tĩnh thông thường của `Parent` chạy trước phần tương ứng của `Child` (và các superclass của `Parent` trước nữa nếu cần). Nếu `Parent` đã initialized thì không chạy lại.

**Câu 2.** Trong cùng class: `static { A(); }`, tiếp đến `static int x = B();`, sau cùng `static { C(); }`. Thứ tự các lời gọi?

**Đáp án:** `A()` → `B()` → `C()`, theo thứ tự văn bản, giả sử không có lỗi hay side effect kích hoạt đường khởi tạo khác làm thay đổi quan sát.

**Câu 3.** Vì sao `Child.PARENT_FIELD` có thể chỉ in log từ `Parent`?

**Đáp án:** Trường được khai báo ở `Parent`; initialization theo lớp **khai báo trường** đối với truy cập static field, không dựa đơn thuần vào kiểu viết trước dấu chấm.

**Câu 4.** `interface Metrics` không có default method, nhưng khai báo `int X = helper();`. Tạo object của lớp `implements Metrics` có chắc chạy initializer của `Metrics` không?

**Đáp án:** Không. Interface không có default method không bị buộc khởi tạo chỉ vì lớp triển khai được khởi tạo. Truy cập `Metrics.X` sẽ yêu cầu initialization vì `helper()` không tạo constant variable.

**Câu 5.** Tạo object thứ hai từ cùng class có chạy lại khối `static`?

**Đáp án:** Không, nếu class definition đã initialized thành công. Các initializer instance và constructor vẫn chạy cho object mới.

## Ghi nhớ

Để dự đoán đúng log và trạng thái khi JVM khởi tạo lớp, hãy lần lượt xác định **hành động thực sự buộc khởi tạo**, **lớp khai báo thành viên**, **chuỗi superclass và superinterface default-method cần thiết**, rồi **thứ tự field initializer / static block từ trên xuống trong mỗi lớp**. Class đã khởi tạo thành công không khởi tạo lại cho lần sử dụng sau. Những trường hợp cần xét riêng là compile-time constant, vòng phụ thuộc, lỗi static initializer và class loader khác nhau.

**Nguồn chuẩn để tra cứu thêm:** Java Language Specification (Java SE 17), §12.4 *Initialization of Classes and Interfaces*, đặc biệt §12.4.1–§12.4.2: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4 ; Java Virtual Machine Specification (Java SE 17), §5.5: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
