# Đọc metadata, nạp lớp và kích hoạt khởi tạo

Khi Reflection trả về một đối tượng `Class<?>`, điều đó không tự chứng minh bộ khởi tạo `static` của lớp đã chạy. Ngược lại, một thao tác có tên nghe giống “chỉ đọc”, như đọc giá trị trường tĩnh, vẫn có thể kích hoạt khởi tạo lớp.

Trong phân cấp sealed, `getPermittedSubclasses()` còn có thể yêu cầu lấy các đối tượng `Class` của những kiểu được cho phép. Vì vậy, cần phân biệt **quan sát metadata**, **nạp hoặc phân giải kiểu** và **thực thi bộ khởi tạo lớp**.

Bài dùng Java 17 trở lên để quan sát ba việc này qua một bộ nạp riêng, thay vì suy đoán trạng thái từ việc đã thấy tên lớp.

## 1. Các khái niệm cần tách riêng

| Khái niệm | Điều đang diễn ra | Không nên suy ra |
| --- | --- | --- |
| Nạp lớp (*loading*) | Tìm và tạo biểu diễn runtime của một lớp từ định nghĩa lớp | Chưa đủ để kết luận mã `static` đã chạy |
| Liên kết (*linking*) | Kiểm tra, chuẩn bị và phân giải các tham chiếu cần thiết | Không đồng nhất với thực hiện các biểu thức khởi tạo tĩnh |
| Khởi tạo lớp (*initialization*) | Thực hiện các biểu thức khởi tạo trường tĩnh và khối `static` theo quy tắc Java | Không phải tạo một đối tượng mới mỗi lần |
| Khởi tạo đối tượng | Tạo một instance và chạy chuỗi constructor của nó | Không có nghĩa bộ khởi tạo lớp chạy lại |

Đây là những giai đoạn được phân biệt trong [JLS về quá trình thực thi Java](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html). Việc phân giải tham chiếu có thể được thực hiện theo cách sớm hoặc muộn mà đặc tả cho phép; đừng suy ra toàn bộ tiến trình liên kết chỉ từ vài dòng log của chương trình.

Bộ khởi tạo lớp thường được nói tới bằng tên đặc biệt `<clinit>` trong bytecode. Nó khác các constructor tạo instance mà bạn lấy qua `getConstructor()`.

## 2. Metadata là thông tin; sử dụng thành viên là hành động khác

Với một lớp thông thường đã xác định:

| Thao tác | Ý nghĩa chính | Có yêu cầu chạy khởi tạo lớp đích không? |
| --- | --- | --- |
| Lấy class literal như `SomeType.class` | Lấy đối tượng mô tả kiểu | Không chỉ vì class literal |
| `Class.forName(name, false, loader)` | Tìm và nạp kiểu qua bộ nạp đã chọn | Không yêu cầu khởi tạo lớp được chỉ tên |
| `Class.forName(name, true, loader)` | Tìm kiểu và yêu cầu khởi tạo | Có, nếu chưa khởi tạo |
| `Class.forName(name)` với tên lớp thông thường | Biến thể có yêu cầu khởi tạo | Có |
| Tìm `Field`, `Method`, `Constructor` | Lấy metadata thành viên | Chưa phải đọc giá trị, gọi phương thức hay tạo instance |
| `Field.get(null)` trên trường tĩnh | Đọc giá trị trường | Có thể khởi tạo lớp khai báo trường |
| `Method.invoke(null, ...)` trên phương thức tĩnh | Thực thi phương thức | Có thể khởi tạo lớp khai báo phương thức |
| `Constructor.newInstance(...)` | Tạo đối tượng qua constructor | Khởi tạo lớp cần thiết trước khi tạo đối tượng nếu chưa có |

Quy tắc của tham số `initialize` và biến thể một tham số nằm trong [API `Class.forName`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)). Tên “Reflection” không quyết định hành vi; thao tác cụ thể mới quyết định.

Ví dụ, `getField("VALUE")` hỏi trường nào tồn tại; `field.get(null)` hỏi giá trị của trường đó. Hai bước liên tiếp nhưng có hệ quả khác nhau.

## 3. Thí nghiệm tách bộ nạp và bộ khởi tạo

Ví dụ có một lớp sealed `Root` và ba lớp con được cho phép. Các dòng bắt đầu bằng `INIT` do mã khởi tạo tĩnh in ra; các dòng `CTOR` do constructor của đối tượng in ra.

Bộ nạp `TrackingLoader` ghi lại những lớp `probe.*` mà chính nó đã định nghĩa thành công. Nó dùng bộ nạp nền tảng làm cha để các lớp thử nghiệm được nạp qua bộ nạp riêng, thay vì được bộ nạp ứng dụng nhận trước.

Tạo năm tệp với cấu trúc:

```text
LifecycleDemo.java
probe/
  Root.java
  LeafA.java
  LeafB.java
  LeafC.java
```

### Tệp `LifecycleDemo.java`

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class LifecycleDemo {
    private static final class TrackingLoader extends URLClassLoader {
        private final Set<String> defined = new HashSet<>();

        TrackingLoader(URL location) {
            super(new URL[]{location}, ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            Class<?> result = super.findClass(name);
            if (name.startsWith("probe.")) {
                defined.add(name);
            }
            return result;
        }

        List<String> definedNames() {
            return defined.stream().sorted().toList();
        }
    }

    private static Class<?> find(Class<?>[] types, String name) {
        return Arrays.stream(types)
                .filter(type -> type.getName().equals(name))
                .findFirst()
                .orElseThrow();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException, IOException {
        URL location = LifecycleDemo.class.getProtectionDomain()
                .getCodeSource().getLocation();
        try (TrackingLoader loader = new TrackingLoader(location)) {
            System.out.println("1. Acquire Root Class without initialization");
            Class<?> root = Class.forName("probe.Root", false, loader);
            System.out.println("Root Class ready");

            System.out.println("2. Read metadata");
            System.out.println("Root sealed = " + root.isSealed());
            Class<?>[] permitted = root.getPermittedSubclasses();
            System.out.println("Permitted = " + Arrays.stream(permitted)
                    .map(Class::getName).sorted().toList());
            System.out.println("Defined after metadata = " + loader.definedNames());

            Field value = root.getField("VALUE");
            Class<?> leafB = find(permitted, "probe.LeafB");
            Class<?> leafC = find(permitted, "probe.LeafC");
            Method ping = leafB.getMethod("ping");
            Constructor<?> constructor = leafC.getConstructor();
            System.out.println("Member metadata ready");

            System.out.println("3. Read static field");
            System.out.println("VALUE = " + value.get(null));

            System.out.println("4. Initialize LeafA explicitly");
            Class.forName("probe.LeafA", true, loader);
            System.out.println("Repeat initialization request");
            Class.forName("probe.LeafA", true, loader);
            System.out.println("Repeat complete");

            System.out.println("5. Invoke static method");
            ping.invoke(null);

            System.out.println("6. Construct LeafC twice");
            constructor.newInstance();
            constructor.newInstance();
        }
    }
}
```

### Tệp `probe/Root.java`

```java
package probe;

public sealed class Root permits LeafA, LeafB, LeafC {
    public static int VALUE = initialize();

    private static int initialize() {
        System.out.println("INIT Root");
        return 42;
    }

    public Root() {
        System.out.println("CTOR Root");
    }
}
```

### Tệp `probe/LeafA.java`

```java
package probe;

public final class LeafA extends Root {
    static {
        System.out.println("INIT LeafA");
    }
}
```

### Tệp `probe/LeafB.java`

```java
package probe;

public final class LeafB extends Root {
    static {
        System.out.println("INIT LeafB");
    }

    public static void ping() {
        System.out.println("CALL LeafB.ping");
    }
}
```

### Tệp `probe/LeafC.java`

```java
package probe;

public final class LeafC extends Root {
    static {
        System.out.println("INIT LeafC");
    }

    public LeafC() {
        System.out.println("CTOR LeafC");
    }
}
```

### Biên dịch và chạy

Tạo thư mục `out`, rồi chạy các lệnh tại thư mục chứa `LifecycleDemo.java`:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror -d out LifecycleDemo.java probe/Root.java probe/LeafA.java probe/LeafB.java probe/LeafC.java
java -cp out LifecycleDemo
```

Kết quả:

```text
1. Acquire Root Class without initialization
Root Class ready
2. Read metadata
Root sealed = true
Permitted = [probe.LeafA, probe.LeafB, probe.LeafC]
Defined after metadata = [probe.LeafA, probe.LeafB, probe.LeafC, probe.Root]
Member metadata ready
3. Read static field
INIT Root
VALUE = 42
4. Initialize LeafA explicitly
INIT LeafA
Repeat initialization request
Repeat complete
5. Invoke static method
INIT LeafB
CALL LeafB.ping
6. Construct LeafC twice
INIT LeafC
CTOR Root
CTOR LeafC
CTOR Root
CTOR LeafC
```

Danh sách lớp được sắp xếp trước khi in để không phụ thuộc thứ tự phần tử của `getPermittedSubclasses()`. Ví dụ quan sát các mốc cần thiết, không cố ghi log mọi lần JVM thực hiện từng bước phân giải nội bộ.

## 4. Đọc từng mốc trong kết quả

### Mốc 1: có `Class` nhưng chưa có `INIT`

`Class.forName("probe.Root", false, loader)` trả đối tượng `Class` cho `Root`. Chương trình in `Root Class ready`, nhưng chưa có `INIT Root`.

Như vậy, “đã có đối tượng `Class`” khác với “bộ khởi tạo lớp đã chạy”. Đây là cơ sở cho công cụ cần kiểm tra cấu trúc trước khi chủ động kích hoạt hành vi của lớp.

`false` cũng không có nghĩa tên lớp chắc chắn hợp lệ hoặc không thể xảy ra lỗi. Việc tìm, nạp và liên kết vẫn có thể gặp lỗi riêng, dù chưa yêu cầu chạy bộ khởi tạo.

### Mốc 2: đọc sealed metadata có thể cần thêm lớp

`getPermittedSubclasses()` trả các kiểu được cho phép của `Root`. Sau bước này, bộ nạp đã định nghĩa `Root`, `LeafA`, `LeafB`, `LeafC`, nhưng không có dòng `INIT` nào của chúng trong kết quả trước mốc 3.

Điều quan sát được là **các lớp đã được định nghĩa để phục vụ việc lấy metadata**, trong khi phần mã khởi tạo tĩnh của chúng chưa thực hiện.

[API `getPermittedSubclasses()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) mô tả việc cố lấy `Class` của các mục bằng bộ nạp định nghĩa kiểu hiện tại. Vì vậy, không xem lời gọi này như việc chỉ sao chép một danh sách các lớp vốn đã được nạp trước đó.

Sau đó, chương trình lấy `Field`, `Method` và `Constructor`. Dòng `Member metadata ready` vẫn xuất hiện trước mọi dòng `INIT`. Chưa có giá trị trường được đọc, phương thức đích được gọi hay đối tượng thử nghiệm được tạo.

### Mốc 3: đọc giá trị trường tĩnh

Lời gọi `value.get(null)` làm `Root` khởi tạo, nên `INIT Root` xuất hiện trước `VALUE = 42`.

`null` ở đây là đối tượng nhận không cần dùng cho trường `static`; nó không có nghĩa giá trị trường bằng `null`.

Quy tắc khởi tạo lớp khai báo trường khi đọc giá trị tĩnh qua Reflection được nêu trong [API `Field.get`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#get(java.lang.Object)). Ví dụ dùng trường `int VALUE` được khởi tạo qua một lời gọi phương thức để việc quan sát không bị nhầm với hằng biên dịch.

### Mốc 4: yêu cầu khởi tạo tường minh

`Class.forName("probe.LeafA", true, loader)` chạy khởi tạo `LeafA`. `Root` đã khởi tạo thành công ở mốc 3 nên không chạy lại.

Lặp lại cùng yêu cầu không tạo thêm dòng `INIT LeafA`. Với chính định nghĩa lớp đó, khởi tạo thành công không được thực hiện lại mỗi khi chương trình yêu cầu sử dụng.

### Mốc 5: gọi phương thức tĩnh

Tìm `Method ping` trước đó chưa chạy nội dung của `ping`. Đến `ping.invoke(null)`, chương trình khởi tạo `LeafB`, rồi mới in `CALL LeafB.ping` từ phần thân phương thức.

Đó là hai hành động khác nhau có thể diễn ra trong cùng lời gọi: bảo đảm lớp được khởi tạo rồi thực thi phương thức. [API `Method.invoke`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)) quy định hành vi này đối với phương thức tĩnh.

### Mốc 6: tạo hai đối tượng

Lần `newInstance()` đầu tiên chạy `INIT LeafC`, sau đó chạy constructor của `Root` và `LeafC`. Lần thứ hai chỉ chạy hai constructor đối tượng; không có thêm `INIT LeafC`.

Đây là khác biệt giữa **khởi tạo một lớp** và **khởi tạo từng instance**. [API `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) nêu việc khởi tạo lớp khai báo constructor trước khi tạo instance nếu cần.

## 5. Lớp cha, interface và nơi thực sự khai báo thành viên

Nếu một lớp con cần được khởi tạo trước khi lớp cha đã hoàn tất khởi tạo, Java khởi tạo lớp cha theo quy tắc tương ứng trước. Trong thí nghiệm, `Root` được khởi tạo sớm bởi việc đọc `VALUE`, nên các mốc sau không cần chạy lại phần đó.

Không mở rộng máy móc thành kết luận rằng “khởi tạo một interface luôn khởi tạo mọi superinterface”. Quy tắc interface và các interface có phương thức mặc định có những điều kiện riêng trong đặc tả.

Với thành viên tĩnh kế thừa, cần chú ý lớp **thực sự khai báo** thành viên. Việc tra cứu một trường qua kiểu con không tự biến trường đó thành trường do kiểu con khai báo. Có thể dùng `getDeclaringClass()` trên `Field` hoặc `Method` để giữ thông tin này trong báo cáo.

Những chi tiết này giúp giải thích vì sao log `INIT` không nhất thiết xuất hiện ở kiểu mà người đọc mã đang nhìn bằng mắt đầu tiên.

## 6. Không biến “không khởi tạo” thành “không có tác động”

Tham số `false` kiểm soát yêu cầu khởi tạo đối với lớp được chỉ tên. Nó không biến một bộ nạp tùy biến thành mã thuần túy chỉ đọc bộ nhớ.

Bộ nạp có thể tìm tệp, đọc tài nguyên hoặc thực hiện logic của chính nó. Việc phân giải metadata cũng có thể cần những kiểu khác. Vì vậy, một công cụ nên nói rõ nó tránh **chủ động khởi tạo lớp đích**, thay vì tuyên bố rằng mọi bước khám phá đều không thể thực thi bất kỳ mã hay thao tác nào.

Cũng không thể đo trạng thái khởi tạo chỉ bằng việc một lớp đã xuất hiện trong danh sách của bộ nạp hoặc danh sách các lớp đã nạp. Thí nghiệm có một mốc mà cả bốn lớp đã được định nghĩa nhưng chưa lớp thử nghiệm nào in `INIT`.

Ngược lại, đọc giá trị một trường tĩnh hoặc gọi một phương thức để “thử xem lớp đã khởi tạo chưa” có thể chính là hành động kích hoạt khởi tạo, làm thay đổi điều bạn định quan sát.

## 7. Lỗi và thời điểm quan sát

Nên phân biệt các nhóm lỗi:

| Bước | Ví dụ vấn đề |
| --- | --- |
| Tìm và nạp lớp | Không tìm thấy lớp qua bộ nạp đã chọn |
| Liên kết hoặc phân giải | Định nghĩa lớp hay phụ thuộc không phù hợp |
| Khởi tạo lớp | Biểu thức trường tĩnh hoặc khối `static` thất bại |
| Gọi thành viên sau đó | Sai quyền truy cập, sai đối số hoặc phần thân đích ném ngoại lệ |

Lỗi trong quá trình khởi tạo tĩnh có thể xuất hiện dưới dạng `ExceptionInInitializerError`. Sau một lần khởi tạo thất bại, lần sử dụng tiếp theo còn có thể báo `NoClassDefFoundError` do lớp ở trạng thái lỗi; không phải mọi lỗi mang tên này đều chỉ là thiếu một tệp `.class`.

Đừng đồng nhất lỗi khởi tạo lớp với ngoại lệ được ném từ phần thân phương thức hoặc constructor đích. Với lời gọi Reflection, thời điểm thất bại ảnh hưởng đến cách ngoại lệ được đưa ra hoặc bọc lại; cần giữ nguyên nguyên nhân khi phân tích.

Khởi tạo thành công là trạng thái của một định nghĩa lớp cụ thể. Hai bộ nạp khác nhau có thể định nghĩa hai lớp cùng tên nhị phân nhưng có trạng thái khởi tạo riêng. Trong thí nghiệm, bộ nạp riêng giúp giữ bối cảnh quan sát rõ ràng.

`close()` của `URLClassLoader` dùng để đóng tài nguyên do bộ nạp quản lý; nó không có nghĩa JVM lập tức dỡ mọi lớp đã được định nghĩa hoặc đặt lại bộ khởi tạo của chúng.

## 8. Cách tổ chức công cụ Reflection

Một luồng xử lý dễ kiểm chứng là:

1. Chọn đúng bộ nạp và lấy `Class` với chính sách khởi tạo phù hợp.
2. Đọc metadata cần thiết, như sealed, thành viên và chữ ký.
3. Xác minh điều kiện của công cụ mà chưa dùng việc gọi thử thành viên làm phép kiểm tra cấu trúc.
4. Chỉ ở bước cần thực thi mới đọc giá trị tĩnh, gọi phương thức hoặc tạo đối tượng.
5. Báo lỗi theo đúng bước để không nhầm thiếu metadata với lỗi khởi tạo.

Cách phân chia này đặc biệt hữu ích khi xây danh mục kiểu, kiểm tra phân cấp sealed hoặc chuẩn bị bộ chuyển đổi dữ liệu. Nó giúp giải thích hành động nào có thể làm mã ứng dụng bắt đầu chạy.

## 9. Lỗi thường gặp và tự kiểm tra

| Suy luận sai | Phân biệt cần giữ |
| --- | --- |
| Có `Class<?>` là static initializer đã chạy | Biểu diễn kiểu so với trạng thái khởi tạo |
| Chỉ đọc metadata nên không thể nạp thêm lớp | Metadata có thể cần lấy hoặc phân giải kiểu liên quan |
| `Class.forName(name)` giống biến thể truyền `false` | Chính sách khởi tạo của từng overload |
| Lấy được `Method` nghĩa là đã gọi phương thức | Metadata so với `invoke` |
| Tìm `Field` giống đọc giá trị trường | `getField` so với `Field.get` |
| Mỗi `newInstance()` chạy lại bộ khởi tạo tĩnh | Khởi tạo lớp so với constructor từng đối tượng |
| `false` bảo đảm không có tác động nào từ bộ nạp | Khởi tạo lớp đích so với logic nạp lớp |
| Đọc thành viên qua lớp con luôn khởi tạo chính lớp con | Kiểu dùng để tra cứu so với lớp khai báo thành viên |

Hãy thử thay đổi từng mốc trong thí nghiệm:

1. Bỏ bước đọc `VALUE`: trước khi `INIT LeafA`, phần khởi tạo nào cần được thực hiện?
2. Giữ việc tìm `ping` nhưng bỏ `ping.invoke(null)`: tại sao `INIT LeafB` không xuất hiện chỉ vì đã có `Method`?
3. Chỉ tạo một đối tượng `LeafC`: số dòng `INIT` và `CTOR` thay đổi thế nào?
4. Đổi lần `Class.forName` đầu tiên từ `false` sang `true`: `INIT Root` chuyển tới vị trí nào?
5. Tại sao không thể dùng `value.get(null)` làm một phép hỏi thụ động rằng lớp đã khởi tạo chưa?

Hãy theo dõi riêng **đối tượng `Class` đã có**, **những kiểu được nạp hoặc phân giải**, và **mã khởi tạo đã được kích hoạt**. Ba thông tin này liên quan với nhau nhưng không thay thế cho nhau.
