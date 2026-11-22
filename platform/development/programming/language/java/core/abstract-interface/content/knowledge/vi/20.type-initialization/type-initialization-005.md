# Khởi tạo lớp và các interface cha có khai báo default method

Khi Java khởi tạo một lớp, JVM không chỉ xử lý lớp cha theo quan hệ kế thừa lớp. Java còn khởi tạo các superinterface có khai báo phương thức `default` của lớp đó trước khi chạy các trình khởi tạo `static` của lớp. Quy tắc này bảo đảm các interface liên quan đã được khởi tạo trước khi mã của lớp bắt đầu thực thi.

Điểm quan trọng là **không phải mọi interface mà lớp triển khai đều tự động được khởi tạo**. Quy tắc đặc biệt áp dụng cho các superinterface khai báo phương thức `default`; interface khác chỉ được khởi tạo khi có một thao tác chủ động sử dụng nó.

## 1. Khi nào một lớp được khởi tạo?

Khởi tạo lớp (*class initialization*) là quá trình thực thi các bộ khởi tạo biến `static` và khối `static` của lớp theo thứ tự xuất hiện trong mã nguồn. Quá trình này khác với khởi tạo đối tượng (*instance initialization*), vốn bao gồm các giá trị khởi tạo trường instance, khối khởi tạo instance và constructor.

Một lớp thường được khởi tạo ngay trước lần đầu xảy ra một thao tác chủ động sử dụng lớp, chẳng hạn:

- Tạo đối tượng bằng `new`.
- Gọi một phương thức `static` được khai báo trong lớp.
- Gán cho trường `static` được khai báo trong lớp.
- Đọc trường `static` được khai báo trong lớp, nếu trường đó không phải biến hằng compile-time.

Khi lớp được khởi tạo lần đầu, Java thực hiện các bước theo thứ tự khái quát:

1. Khởi tạo superclass trước.
2. Khởi tạo các superinterface của lớp có khai báo phương thức `default`, theo thứ tự liệt kê đệ quy mà Java quy định.
3. Chạy các bộ khởi tạo trường `static` và khối `static` của chính lớp, theo thứ tự văn bản trong lớp.

Nếu lớp cha hoặc một superinterface cần thiết đã được khởi tạo trước đó, Java không khởi tạo nó lần thứ hai. Một lớp hoặc interface chỉ trải qua quá trình khởi tạo một lần trong vòng đời của class loader tương ứng.

## 2. Vì sao interface có default method được xử lý đặc biệt?

`default method` là phương thức instance có phần thân được khai báo trong interface. Nó cho phép các lớp triển khai kế thừa một hành vi mặc định mà không cần tự viết lại phương thức đó.

Ví dụ:

~~~java
interface Auditable {
    int INITIALIZED = InitLog.mark("Auditable");

    default void audit() {
        System.out.println("audit");
    }
}
~~~

Trường `INITIALIZED` là trường `public static final` theo quy tắc của interface. Giá trị của nó được tính bằng lời gọi phương thức, nên không phải biến hằng compile-time. Khi interface `Auditable` được khởi tạo, lời gọi `InitLog.mark(...)` sẽ được thực thi.

Nếu một lớp triển khai `Auditable`, quá trình khởi tạo lớp sẽ khởi tạo interface `Auditable` trước khi chạy các trình khởi tạo `static` của lớp. Điều này vẫn đúng ngay cả khi chương trình không gọi `audit()` trong quá trình tạo đối tượng.

Java xét các superinterface trong quan hệ kế thừa đệ quy, không chỉ các interface được liệt kê trực tiếp trên lớp. Vì vậy, nếu `Child` kế thừa một `default method` từ `Parent`, thì `Parent` vẫn thuộc nhóm interface cần xét khi khởi tạo một lớp triển khai `Child`.

Cần phân biệt hai khái niệm:

- **Khai báo `default method`:** interface tự khai báo một phương thức `default`.
- **Kế thừa `default method`:** interface nhận phương thức mặc định từ interface cha nhưng không tự khai báo phương thức đó.

Một interface chỉ kế thừa phương thức mặc định mà không tự khai báo `default method` không được chọn chỉ vì nó kế thừa phương thức ấy. Tuy nhiên, interface cha thực sự khai báo phương thức mặc định vẫn được xét riêng trong quá trình duyệt các superinterface.

## 3. Ví dụ Java 17+ có thể chạy

Lưu chương trình sau vào tệp `DefaultInterfaceInitialization.java`.

~~~java
class InitLog {
    static int mark(String name) {
        System.out.println(name);
        return 0;
    }
}

class Base {
    static int initialized = InitLog.mark("Base");
}

interface PlainParent {
    int initialized = InitLog.mark("PlainParent");
}

interface RootDefault {
    int initialized = InitLog.mark("RootDefault");

    default void root() {
    }
}

interface ChildWithDefault extends PlainParent, RootDefault {
    int initialized = InitLog.mark("ChildWithDefault");

    default void child() {
    }
}

interface Marker {
    int initialized = InitLog.mark("Marker");
}

class Sample extends Base implements ChildWithDefault, Marker {
    static int initialized = InitLog.mark("Sample");
}

public class DefaultInterfaceInitialization {
    public static void main(String[] args) {
        System.out.println("start");

        new Sample();
        System.out.println("instance ready");

        // Lần khởi tạo Sample thứ hai không chạy lại các initializer.
        new Sample();

        // Marker không khai báo default method, nên chỉ được khởi tạo
        // khi trường non-constant của chính interface được đọc.
        System.out.println("Marker value=" + Marker.initialized);
        System.out.println("PlainParent value=" + PlainParent.initialized);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac DefaultInterfaceInitialization.java
java DefaultInterfaceInitialization
~~~

Kết quả chuẩn:

~~~text
start
Base
RootDefault
ChildWithDefault
Sample
instance ready
Marker
Marker value=0
PlainParent
PlainParent value=0
~~~

### Đọc kết quả theo thứ tự

**`start` xuất hiện đầu tiên.** Chưa có thao tác nào yêu cầu khởi tạo `Sample`, nên các initializer chưa chạy.

**`Base` xuất hiện trước.** Lệnh `new Sample()` cần khởi tạo lớp `Sample`, vì vậy superclass `Base` được khởi tạo trước. Trường `Base.initialized` gọi `InitLog.mark("Base")`, tạo dòng `Base`.

**`RootDefault` xuất hiện trước `ChildWithDefault`.** `Sample` triển khai `ChildWithDefault`; interface này có khai báo `default method`. Khi duyệt các superinterface, Java gặp `RootDefault`, vốn cũng tự khai báo `default method`, trước khi khởi tạo `ChildWithDefault`. Cả hai interface được khởi tạo trước phần `static` của `Sample`.

**`Sample` xuất hiện sau các interface đủ điều kiện.** Lúc này superclass và các superinterface cần khởi tạo đã hoàn tất, nên trường `static` của `Sample` mới được xử lý.

**`instance ready` xuất hiện sau khi `new Sample()` hoàn tất.** Việc tạo đối tượng chỉ hoàn tất sau khi lớp đã được khởi tạo và quá trình khởi tạo instance chạy xong.

**Lần `new Sample()` thứ hai không in thêm dòng khởi tạo.** Java không chạy lại các initializer khi lớp đã khởi tạo thành công.

**`Marker` và `PlainParent` chỉ xuất hiện ở cuối.** Hai interface này không tự khai báo `default method`, nên không được tự động khởi tạo chỉ vì `Sample` triển khai hoặc gián tiếp kế thừa chúng. Đọc trường `initialized` của từng interface là thao tác chủ động sử dụng trường `static` không phải hằng compile-time, vì vậy nó kích hoạt việc khởi tạo interface tương ứng.

Các trường `initialized` trong interface là `public static final`, nhưng không phải biến hằng compile-time vì giá trị của chúng đến từ lời gọi phương thức. Do đó, việc đọc chúng thực sự kích hoạt khởi tạo interface.

## 4. Thứ tự initializer bên trong một kiểu

Khi một lớp hoặc interface bắt đầu khởi tạo, các initializer của chính kiểu đó chạy theo thứ tự xuất hiện trong mã nguồn. Ví dụ:

~~~java
class Example {
    static int first = log("first");

    static {
        log("static block");
    }

    static int last = log("last");

    static int log(String message) {
        System.out.println(message);
        return 0;
    }
}
~~~

Khi `Example` được khởi tạo, thứ tự là:

~~~text
first
static block
last
~~~

Đối với một lớp có superclass và các superinterface khai báo `default method`, thứ tự bên ngoài là: superclass, các superinterface đủ điều kiện theo thứ tự quy định, rồi mới đến các initializer `static` của lớp. Bên trong từng kiểu, các initializer của chính kiểu đó vẫn theo thứ tự văn bản.

## 5. Khởi tạo interface trực tiếp khác với khởi tạo lớp

Một interface cũng có thể được khởi tạo bởi thao tác chủ động sử dụng chính interface đó, chẳng hạn gọi phương thức `static` của nó hoặc đọc một trường `static` không phải biến hằng compile-time.

Tuy nhiên, **khởi tạo một interface trực tiếp không tự động khởi tạo tất cả superinterface của nó**. Quy tắc khởi tạo các superinterface có `default method` được áp dụng khi khởi tạo một lớp. Không nên suy luận rằng mọi interface cha đều được khởi tạo mỗi khi một interface con được sử dụng.

Một trường `static final` có giá trị hằng compile-time, chẳng hạn `int LIMIT = 10`, có thể được trình biên dịch thay trực tiếp bằng giá trị hằng. Chỉ đọc trường như vậy không kích hoạt khởi tạo interface khai báo nó. Ngược lại, một trường được gán bằng lời gọi phương thức như `int value = compute()` không phải biến hằng compile-time, nên đọc trường sẽ kích hoạt khởi tạo interface.

## 6. Lỗi dễ gặp

- **Cho rằng tất cả interface đều được khởi tạo cùng lớp:** Java tự động xử lý superclass và các superinterface khai báo `default method`. Interface còn lại có thể vẫn chưa được khởi tạo.
- **Cho rằng phải gọi `default method` thì interface mới khởi tạo:** không đúng. Việc khởi tạo lớp triển khai đã khiến các superinterface đủ điều kiện được khởi tạo, dù phương thức mặc định chưa được gọi.
- **Nhầm khởi tạo lớp với khởi tạo đối tượng:** initializer `static` chạy khi lớp được khởi tạo; initializer instance và constructor chạy trong quá trình tạo từng đối tượng.
- **Quên thứ tự giữa superclass, interface và lớp:** initializer `static` của lớp con không chạy trước superclass và các superinterface cần khởi tạo.
- **Cho rằng interface cha luôn khởi tạo trước khi interface con được sử dụng:** khởi tạo trực tiếp một interface không tự động kéo theo toàn bộ superinterface. Hãy xác định thao tác chủ động sử dụng và phân biệt nó với quá trình khởi tạo một lớp.
- **Nhầm `static final` với hằng compile-time:** `final` không đủ để kết luận một trường là biến hằng. Giá trị phải là biểu thức hằng theo quy tắc Java; lời gọi phương thức không đáp ứng điều kiện đó.

## 7. Quy trình phân tích một tình huống

Khi cần xác định thứ tự in ra từ các initializer, hãy làm theo các bước sau:

1. Xác định thao tác nào kích hoạt khởi tạo lớp hoặc interface.
2. Nếu đó là lớp, xác định superclass và các superinterface trong quan hệ kế thừa đệ quy có tự khai báo `default method`.
3. Đánh dấu các kiểu đã được khởi tạo trước đó; chúng không chạy lại initializer.
4. Ghi thứ tự khởi tạo superclass, các superinterface đủ điều kiện, rồi các initializer `static` của lớp.
5. Trong mỗi kiểu, đọc initializer trường `static` và khối `static` theo thứ tự văn bản.
6. Sau khi hoàn thành khởi tạo lớp, mới xét quá trình khởi tạo instance và constructor nếu thao tác ban đầu là `new`.

Cách phân tích này giúp dự đoán chính xác thứ tự khởi tạo, tránh các lỗi phụ thuộc vào thứ tự initializer và hiểu vì sao một số interface được khởi tạo sớm hơn những interface khác.