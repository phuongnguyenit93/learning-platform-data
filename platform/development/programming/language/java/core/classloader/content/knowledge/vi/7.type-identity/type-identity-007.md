# Loading constraint bảo đảm nhất quán kiểu trong chữ ký

## 1. Vấn đề: cùng một tên Java có thể chỉ hai kiểu khác nhau

Trong JVM, class/interface ở runtime được xác định bởi **tên nhị phân (binary name) và defining class loader**. Nếu hai class loader độc lập cùng định nghĩa `com.example.Message`, chúng tạo ra **hai runtime type khác nhau**, dù file class, tên package và tên class giống hệt.

Điều này rất quan trọng ở ranh giới giữa hai loader. Giả sử code thuộc loader `L_A` gọi một phương thức của class do loader `L_B` định nghĩa:

```java
Message transfer(Message input);
```

Nếu `Message` mà mỗi loader thấy là **hai runtime class khác nhau**, cách hai bên hiểu chữ ký sẽ không còn nhất quán: một bên nghĩ tham số/trả về thuộc `Message` của `L_A`, bên kia dùng `Message` của `L_B`. JVM phải bảo vệ tính an toàn kiểu khi giải quyết (*resolve*) những field và method references như vậy.

**Loading constraint** là quy tắc liên kết do JVM áp đặt để bảo đảm các tên kiểu tham chiếu trong field/method descriptor của các class liên quan chỉ tới **cùng runtime type khi sự liên kết đòi hỏi chúng phải là một**.

Điểm mấu chốt:

- Hai loader **được phép** định nghĩa hai class cùng tên nếu chưa có ràng buộc buộc chúng phải được xem như một.
- Khi linking của field/method hoặc quan hệ override/implement đòi cùng một kiểu trong chữ ký, JVM áp đặt loading constraint.
- Nếu loader đã thấy hai định nghĩa không tương thích, hoặc về sau một loader cố ghi nhận class gây vi phạm constraint đã có, thao tác liên quan thất bại bằng **`LinkageError`**.
- Loading constraint thuộc **ngữ nghĩa của JVM**; không phải một Java annotation, dòng cấu hình của loader hay lời gọi API mà ứng dụng cần thực hiện trực tiếp.

Đặc tả nền tảng là **JVMS `5.3.4` — Loading Constraints**; các thời điểm áp đặt được mô tả ở **`5.4.2`** và **`5.4.3`**.

## 2. Ôn lại: defining loader, initiating loader và runtime type identity

Để hiểu loading constraint, cần phân biệt hai vai trò của class loader:

| Khái niệm | Ý nghĩa |
|---|---|
| **Defining loader** | Loader thực sự gọi cơ chế định nghĩa class và sở hữu runtime class identity. |
| **Initiating loader** | Loader đã yêu cầu việc nạp class và được JVM ghi nhận là initiating loader của class đó; có thể nhận class do parent định nghĩa. |
| **Binary name** | Tên ở dạng `com.example.Message` của class, không chứa loader identity. |
| **Runtime class identity** | Cặp tên nhị phân + defining loader; hai class cùng tên nhưng defining loader khác nhau là hai kiểu runtime khác nhau. |

Ví dụ: một custom loader yêu cầu `java.lang.String` thông qua parent delegation. Nó có thể là initiating loader đối với yêu cầu đó, còn bootstrap loader vẫn là defining loader của `String`. `String.class.getClassLoader() == null` trong Java API biểu diễn defining loader bootstrap trên JDK thông thường.

Ký hiệu của JVMS có dạng:

```text
N^L1 = N^L2
```

Đọc là: **tên kiểu N, khi được giải quyết thông qua loader L1 và L2, phải biểu thị cùng một runtime class/interface**. Đây là *loading constraint*, không phải phép so sánh chuỗi tên `N` và cũng không yêu cầu `L1 == L2`.

Nếu hai loader ủy quyền để cùng nhận một class từ loader cha, constraint này thỏa. Nếu hai loader lần lượt định nghĩa hai bản class khác nhau của `N`, constraint đó bị vi phạm.

Một ví dụ trực quan:

```text
                      Shared API
                    (loader Parent)
                        |
          +-------------+-------------+
          |                           |
       Loader A                    Loader B
    impl.A.Service              impl.B.Client
          |                           |
          +------ uses api.Message ---+
                        |
                 Class<Message>
                 do Parent define

Cả A và B cùng resolve api.Message -> một runtime class:
constraint được thỏa mãn.
```

Ngược lại, nếu A và B cùng có bản copy `api.Message` và dùng chính class copy của mình khi tham gia một phương thức chung cần tương thích, JVM có thể phát hiện xung đột qua loading constraint.

## 3. Loading constraint xuất hiện trong chữ ký nào?

JVM lưu kiểu field bằng **field descriptor** và danh sách tham số/kiểu trả về của phương thức bằng **method descriptor**.

Ví dụ:

| Khai báo Java | JVM descriptor |
|---|---|
| `Message message;` | `Lcom/example/Message;` |
| `Message[] messages;` | `[Lcom/example/Message;` |
| `Message transfer(Message input);` | `(Lcom/example/Message;)Lcom/example/Message;` |
| `void accept(Message[][] data);` | `([[Lcom/example/Message;)V` |
| `int count();` | `()I` |

Các tên kiểu tham chiếu như `com/example/Message` là những thành phần có thể chịu loading constraint khi có liên kết yêu cầu tính nhất quán giữa loaders.

Một số chi tiết:

- **Primitive** `int`, `long`, `boolean`... không có danh tính class do custom loader định nghĩa, nên không phải vấn đề “cùng tên nhưng khác defining loader”.
- **Array** gồm các dấu `[` trong descriptor. Đối với mảng của class/interface, ràng buộc được xét theo kiểu phần tử tham chiếu tương ứng; không được kết luận “mảng không liên quan vì tên có `[`”.
- **`void`** là kiểu trả về đặc biệt và không phát sinh một class reference do loader định nghĩa.
- **Generics** như `List<Message>` thông thường bị *erasure* thành `Ljava/util/List;` trong method/field descriptor. Riêng generic argument `Message` **không tự sinh loading constraint chỉ vì nó xuất hiện trong generic signature metadata**. Code khác trực tiếp dùng `Message` vẫn có thể đưa tên đó vào descriptor hoặc symbolic reference riêng.
- Danh sách `throws SomeException` không nằm trong method descriptor; exception declaration **không tự nó** là nguyên nhân gây constraint cùng cách với kiểu tham số/trả về.
- Thông tin annotation, tên parameter và nullability cũng không phải là thành phần của field/method descriptor.

**Đừng nhầm “chuỗi descriptor bằng nhau” với “runtime type giống nhau”.** Hai loader có thể nhìn thấy cùng chuỗi `Lcom/example/Message;` mà giải quyết ra hai class khác nhau. Loading constraint xuất hiện khi JVM cần bảo đảm chúng phải là một cho hoạt động liên kết cụ thể.

## 4. JVM áp đặt constraint ở đâu và khi nào?

JVMS quy định việc áp đặt constraint ở một số hoạt động linking. Không phải cứ gọi `loadClass` là JVM sẽ áp đặt một constraint giữa tất cả loader trên thế giới.

### 4.1. Khi chuẩn bị class có quan hệ override hoặc kế thừa phương thức

Trong **preparation**, nếu class con định nghĩa một instance method có thể override method từ superclass/superinterface, JVM cần bảo đảm các kiểu liên quan trong descriptor của method được hiểu nhất quán giữa defining loader của hai class.

Xét tình huống khái niệm:

```java
// Định nghĩa bởi loader Parent:
package api;

public class Message {}

public class Base {
    public Message echo(Message value) {
        return value;
    }
}
```

```java
// Class Sub thuộc một loader Child:
package plugin;

public class Sub extends api.Base {
    @Override
    public api.Message echo(api.Message value) {
        return value;
    }
}
```

**Hai khối trên là phác thảo mã nguồn của hai thành phần, không phải hai chương trình độc lập đặt trong một file.** Chúng mô tả cách class `Sub` override `Base.echo`.

Method descriptor của hai phương thức là:

```text
(Lapi/Message;)Lapi/Message;
```

JVM cần ràng buộc việc resolve `api.Message` thông qua defining loaders liên quan sao cho cùng chỉ tới **một runtime class**. Nếu Child ủy quyền `api.Message` cho Parent, điều kiện được đáp ứng. Nếu Child cố dùng một bản `api.Message` khác trong ngữ cảnh override này, constraint có thể bị vi phạm khi linking.

Đặc tả còn bao gồm trường hợp class chọn (*select*) method kế thừa để đáp ứng superinterface method; không được đơn giản hóa toàn bộ thành “chỉ method có từ khóa `@Override` mới có constraint”. `@Override` là annotation kiểm tra ở thời điểm biên dịch; JVM quan tâm quan hệ method thực tế trong class file.

### 4.2. Khi resolve field reference

Nếu class do loader `L_Caller` định nghĩa truy cập field được khai báo trong class do loader `L_Owner` định nghĩa, JVM giải quyết symbolic field reference và descriptor của field đó. Các tên class/interface xuất hiện trong **descriptor của field** phải thỏa loading constraints tương ứng giữa hai bên.

Ví dụ:

```java
// Chỉ minh họa việc tham chiếu field qua hai class/loader.
Message value = service.currentMessage;
```

Nếu field descriptor là `Lapi/Message;`, JVM cần bảo đảm việc hiểu `api.Message` của caller và field owner không dẫn đến hai runtime types khác nhau khi resolution áp đặt constraint.

Không phải **mọi** instance field access đều tạo ra xung đột. Nếu hai bên dùng cùng định nghĩa `api.Message` qua parent delegation, constraint được thỏa thuận và không có lỗi.

### 4.3. Khi resolve method/interface method reference

Với lời gọi:

```java
Message output = service.echo(input);
```

symbolic method reference chứa tên method và descriptor, chẳng hạn:

```text
echo:(Lapi/Message;)Lapi/Message;
```

Khi method resolution/interface method resolution thành công về việc tìm method và quyền truy cập, JVM áp đặt loading constraints cho kiểu tham số và kiểu trả về liên quan tới loader khai báo method được chọn và loader của class chứa symbolic reference, theo các quy tắc `5.4.3`.

Điều này bảo đảm caller không sử dụng một `api.Message` khác với ý nghĩa của `api.Message` trong descriptor của method đích.

### 4.4. Constraint được ghi nhận và kiểm tra theo thời điểm

Không nên suy rằng JVM phải load tất cả class có tên trong mọi descriptor ngay khi đọc một `.class`. JVM được phép thực hiện nhiều hoạt động resolution theo nhu cầu. Hệ quả:

1. **Constraint có thể được áp đặt trước khi tên class tham gia đã được một hoặc cả hai loader thực sự load.** Sau đó, việc ghi nhận một initiating loader cho class mới sẽ phải kiểm tra các constraint đang tồn tại.
2. **Nếu cả hai loader đã resolve cùng tên sang hai runtime classes khác nhau**, một constraint mới yêu cầu chúng bằng nhau sẽ thất bại ngay khi được áp đặt.
3. **Nếu constraint tồn tại trước**, hoạt động nạp class không tương thích về sau có thể thất bại khi JVM ghi nhận initiating loader.
4. Khi phát hiện vi phạm, JVM ném `LinkageError`; thao tác tạo constraint hoặc ghi nhận initiating loader tương ứng thất bại, và constraint/ghi nhận mới gây lỗi được rút lại theo đặc tả.

**Thời điểm thông báo lỗi có thể khác nhau** tùy chương trình, đường linking và việc JVM chọn resolution sớm hay muộn. Không nên viết test phụ thuộc một stack trace hoặc một vị trí dòng duy nhất cho mọi JVM.

## 5. Không phải hai loader cùng tên luôn sai

Một ví dụ quan trọng là **cùng binary name vẫn có thể tồn tại hai class runtime khác nhau nếu chưa có ràng buộc bắt chúng đồng nhất**.

Tạo file độc lập **`LoaderIdentityDemo.java`**, chứa class main và một class package-private cùng tệp:

```java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {
    private static final String TARGET = "Payload";

    static class CopyLoader extends ClassLoader {
        CopyLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                throw new ClassNotFoundException(name);
            }

            String resource = name.replace('.', '/') + ".class";
            try (InputStream in =
                         getParent().getResourceAsStream(resource)) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = LoaderIdentityDemo.class.getClassLoader();
        ClassLoader left = new CopyLoader(app);
        ClassLoader right = new CopyLoader(app);

        Class<?> a = left.loadClass(TARGET);
        Class<?> b = right.loadClass(TARGET);

        System.out.println("Same binary name: "
                + a.getName().equals(b.getName()));
        System.out.println("Same runtime type: " + (a == b));
        System.out.println("Left defined by left: "
                + (a.getClassLoader() == left));
        System.out.println("Right defined by right: "
                + (b.getClassLoader() == right));
        System.out.println("Assignable: " + a.isAssignableFrom(b));
    }
}

class Payload {
}
```

Biên dịch và chạy trên **JDK 17+**, tại thư mục chứa tệp:

```bash
javac LoaderIdentityDemo.java
java LoaderIdentityDemo
```

Stdout:

```text
Same binary name: true
Same runtime type: false
Left defined by left: true
Right defined by right: true
Assignable: false
```

### Tại sao ví dụ không tự ném LinkageError?

Hai `CopyLoader` được viết để ưu tiên **tự định nghĩa** chỉ một class tên `Payload` từ chính bytes có trên application class path; còn các lớp khác vẫn ủy quyền lên parent. Vì `left` và `right` là hai defining loaders, chúng tạo hai class khác nhau có cùng tên `Payload`.

Nhưng chương trình **không** tạo một quan hệ override/field/method resolution liên loader nào yêu cầu `Payload` của hai bên phải cùng một kiểu. Do đó việc class `Payload` được nạp độc lập không tự tạo lỗi loading constraint.

Điều này làm rõ giới hạn quan trọng: **tồn tại hai class trùng tên** và **vi phạm loading constraint** là hai việc khác nhau.

> Code này cố ý child-first với `Payload` để minh họa class identity. Đây không phải khuôn mẫu dùng cho mọi package: không nên áp dụng child-first bừa bãi cho namespace hệ thống, API dùng chung hoặc mọi dependency khi xây dựng plugin.

## 6. Minh họa một tình huống vi phạm constraint

Giả sử host định nghĩa:

```text
Loader Parent:
  api.Message
  api.Service
    public api.Message transfer(api.Message input)
```

Loader plugin `Child` phải override method `transfer` của `api.Service` hoặc gọi method đó qua symbolic reference. Tuy nhiên plugin lại muốn định nghĩa riêng `api.Message` với **cùng binary name** nhưng khác defining loader.

```text
                 Parent defines:
              api.Message [P]
              api.Service [P]
                       |
                       | method descriptor:
                       | (Lapi/Message;)Lapi/Message;
                       |
                Plugin Child
                defines its own:
              api.Message [C]  != [P]
                       |
                       v
       JVM requires api.Message^Child
                 == api.Message^Parent
                       |
                       v
          Conflict: [C] != [P]
                       |
                       v
                  LinkageError
```

Trong tình huống đó, nếu JVM phải áp đặt loading constraint `api.Message^Child = api.Message^Parent` do preparation/method resolution, nó sẽ kiểm tra xem cùng tên có resolve ra cùng runtime class hay không.

Nếu Child đã cố định bản `api.Message` riêng, ràng buộc bị vi phạm. Nếu chưa nạp, constraint được thiết lập có thể khiến lần Child cố định nghĩa bản riêng sau đó thất bại.

Một thông báo trên HotSpot có thể chứa cụm `loader constraint violation`, tên class và mô tả loader liên quan; **không được giả định nội dung hoặc thời điểm chính xác của message trên mọi phiên bản JVM**.

### Cách thiết kế đúng

Nếu `api.Message` là DTO hoặc contract dùng chung:

- Đặt `api.Message` và `api.Service` trong module/JAR API được một loader chia sẻ định nghĩa.
- Cho plugin loader **ủy quyền** tới defining loader của API cho namespace `api.*`.
- Chỉ dùng chiến lược nạp riêng cho các class plugin thực sự cần cách ly; tránh đóng gói/định nghĩa lặp bản API ở plugin khi giao tiếp với host.
- Khi tạo object và truyền qua boundary, xác nhận lớp mà caller và callee dùng là **cùng runtime class**.

Nói cách khác, package trùng tên trong JAR không tạo ra type identity chung; **cách loader resolve class** mới quyết định.

## 7. Loading constraint khác ClassCastException thế nào?

Các lỗi cùng xuất hiện trong hệ thống nhiều class loader nhưng có nguyên nhân và thời điểm khác nhau.

| Hiện tượng | Đặc điểm |
|---|---|
| **`LinkageError` do loading constraint violation** | JVM phát hiện tên kiểu phải nhất quán giữa loaders vì preparation/resolution nhưng thực tế (hoặc thao tác nạp mới) không thể thỏa; thất bại trong loading/linking. |
| **`ClassCastException`** | Tại runtime, một object không thuộc kiểu mà phép ép kiểu yêu cầu; hai class trùng tên nhưng khác defining loader có thể gây lỗi ép kiểu. |
| **`ClassNotFoundException`** | Loader được yêu cầu tìm class nhưng không tìm được; không có nghĩa có hai bản xung đột. |
| **`NoClassDefFoundError`** | JVM không thể tìm hoặc dùng định nghĩa class cần thiết khi executing/linking; cũng có thể liên quan initialization đã lỗi. Không đồng nghĩa mặc định với loading constraint violation. |
| **`NoSuchMethodError`** | Resolution không tìm thấy method có tên/descriptor phù hợp; khác việc tìm được method nhưng descriptor của các bên gây constraint conflict. |

Một ví dụ:

- Nếu app có `Foo` của loader A và đưa object thuộc `Foo` do loader B định nghĩa vào phép ép kiểu sang A, ta có thể gặp **`ClassCastException`**.
- Nếu JVM phải link một lời gọi/override đòi `Foo` của A và B là cùng kiểu trong descriptor nhưng chúng đã khác nhau, ta có thể gặp **`LinkageError`** trước khi có cơ hội thực hiện phép ép kiểu.

Không cần gây cả hai loại lỗi mới kết luận loader bị cấu hình thiếu nhất quán. Hãy tìm chính xác giai đoạn lỗi: **lookup**, **linking**, **initialization** hay **runtime cast**.

## 8. Loading constraints, method overriding và descriptor JVM

### Override ở mức class file

Trong mã nguồn Java, override được kiểm tra theo các quy tắc ngôn ngữ. Ở JVM, việc một instance method có thể override method khác được xác định dựa trên tên, **method descriptor** và các điều kiện access/inheritance tương ứng (JVMS `5.4.5`).

Vì method descriptor chứa **kiểu tham số và kiểu trả về**, việc hai method có cùng descriptor chuỗi chưa bảo đảm đã dùng cùng runtime types nếu class được định nghĩa bởi hai loader khác nhau.

Loading constraints bổ sung điều kiện nhất quán cho các tên tham chiếu trong descriptor khi JVM chuẩn bị class có quan hệ override thích hợp.

### Generic không giải quyết class identity

Ví dụ:

```java
public java.util.List<api.Message> fetch() {
    return java.util.List.of();
}
```

Descriptor JVM sau erasure của method trên là:

```text
()Ljava/util/List;
```

Tên `api.Message` của type argument thường nằm trong metadata generic `Signature`, không nằm trong **method descriptor** này. Vì thế không thể nói JVM bắt buộc tạo loading constraint cho `api.Message` **chỉ vì** nó xuất hiện trong `List<api.Message>`.

Điều này không làm type argument an toàn xuyên loader. Khi code thực sự truy cập, ép kiểu hoặc gọi API dùng `api.Message` trong descriptor, các cơ chế linkage và cast tương ứng vẫn cần được tuân thủ.

### Mảng của kiểu tham chiếu

Method:

```java
api.Message[] copy(api.Message[][] data)
```

có descriptor:

```text
([[Lapi/Message;)[Lapi/Message;
```

Trong ràng buộc liên quan đến method descriptor, tên kiểu phần tử `api.Message` vẫn phải được resolve nhất quán. Không thể dùng khác biệt số chiều mảng để né yêu cầu cùng runtime element type khi JVM áp đặt constraint.

### Primitive không làm nảy sinh xung đột cùng tên loader

Method `int count(long value)` có descriptor `(J)I`. `J` và `I` mô tả primitive được JVM xác định sẵn; không có một custom class loader A định nghĩa “int A” và loader B định nghĩa “int B”.

Tất nhiên một class có method primitive vẫn chịu các quy tắc linking khác; chỉ riêng việc dùng `int`/`long` trong descriptor không đòi loading constraint cho một class reference.

## 9. Constraint không buộc mọi class cùng tên trong JVM phải hợp nhất

Đây là ngộ nhận nguy hiểm khi xây kiến trúc plugin.

**Loading constraints là những quan hệ bình đẳng cụ thể** mà JVM áp đặt khi cần bảo đảm type-safe linkage. Chúng không có nghĩa Java toàn cục chỉ cho phép một `com.example.Widget`.

Hãy xét hai plugin hoàn toàn độc lập:

```text
Plugin A (loader A): com.example.Widget
Plugin B (loader B): com.example.Widget
```

Nếu không có API signature/override/field resolution đòi tên `Widget` ở A và B phải giống nhau, JVM có thể giữ cả hai runtime classes. Điều này có thể là mục đích của classloader isolation.

Nhưng nếu host khai báo:

```text
shared.PluginApi:
  Widget convert(Widget input)
```

và A/B cần thực thi qua API chung, kiểu `Widget` trong chữ ký API phải được thiết kế để các bên resolve thống nhất. Cách an toàn thường là đưa DTO/interface chung vào **shared API loader**. Không cố dùng tên trùng nhau như một hình thức ép hai loader có cùng kiểu.

Cần phân biệt ba tầng:

1. **Tên có trùng nhau không?** So sánh `Class.getName()`.
2. **Runtime class có cùng identity không?** So sánh hai `Class<?>` bằng `==`.
3. **Linking có buộc cùng identity không?** Xét field/method descriptor, override, interface method selection và những symbolic references cụ thể của JVMS.

Hai câu đầu là quan sát trạng thái; câu thứ ba liên quan điều kiện mà JVM phải cưỡng chế khi liên kết.

## 10. Parent delegation hỗ trợ đáp ứng constraints, nhưng không thay thế chúng

Trong mô hình parent-first thông thường:

```text
App loader
    |
    v
Parent loader (định nghĩa api.Message)
    |
    +--> Plugin loader A yêu cầu api.Message
    |
    +--> Plugin loader B yêu cầu api.Message
```

Hai plugin có thể nạp rất nhiều implementation classes riêng biệt, nhưng với namespace `api.Message`, cả hai nhận về cùng định nghĩa của Parent. Khi một loading constraint yêu cầu kiểu này nhất quán, điều kiện được thỏa.

Tuy nhiên:

- **Parent-first không phải luật cứng cho mọi custom loader.** Một loader override `loadClass` có thể ưu tiên tự định nghĩa một số package.
- **Có cùng parent không bảo đảm mọi class cùng tên đều có identity chung.** Nếu hai loader tự override/định nghĩa cùng một tên class trước khi delegation, chúng vẫn có thể tạo hai class.
- **Constraint là quy tắc JVM**, không phải hệ quả tình cờ của việc tuân thủ parent-first.
- **Parent null** thường ủy quyền tới bootstrap với implementation `ClassLoader.loadClass` mặc định. Điều này giúp thống nhất các class lõi, nhưng parent-null không tự nhìn thấy mọi API ở application loader. Nếu DTO/interface dùng chung không thuộc bootstrap, phải chọn loader architecture hợp lý.

Kiến trúc plugin nên có quy tắc package cụ thể: core/JDK từ platform/bootstrap, shared contracts từ một loader chung, implementation riêng từ plugin loader; cân nhắc kỹ module boundaries, dependency visibility và lifecycle.

## 11. Điều tra lỗi loading constraint trong ứng dụng thật

Khi thấy `LinkageError` và thông điệp liên quan `loader constraint violation`, đừng vội đổi tên class hoặc xóa sạch mọi JAR. Phân tích theo đường liên kết:

1. **Đọc tên kiểu trong lỗi**: class/interface nào mà hai loader không thống nhất? Tên đó có nằm trong kiểu field, parameter hoặc return type của API bị liên kết không?
2. **Xác định hai loaders**: ai định nghĩa caller/callee, superclass/subclass hoặc interface/implementation? So sánh class loader identity, không chỉ tên loader hiển thị.
3. **Xem descriptor JVM của field/method**: dùng `javap -s -p` để nhìn kiểu thật sau erasure. Nếu cần override/bridge analysis, dùng `javap -v -p` để xem method, flags và `Signature`.
4. **Kiểm tra dependency duplication**: plugin có đóng gói bản copy của shared interface/DTO/JAR trong chính nó không? Parent delegation có bị override cho namespace chung không?
5. **So sánh `Class<?>` trực tiếp khi có thể**: hai kiểu tên giống nhau nhưng `==` khác nhau là dấu hiệu loader identity khác; cần xác định nơi liên kết đòi đồng nhất.
6. **Đừng phụ thuộc vào lúc lỗi xuất hiện**: resolution có thể lazy. Việc lỗi xảy ra ở lần gọi method đầu tiên không khẳng định nguyên nhân vừa mới được tạo tại lệnh đó.
7. **Sửa ở kiến trúc loader/class path**: thống nhất nơi sở hữu shared API và tránh tạo nhiều bản class có vai trò contract chung. Sau khi sửa, tạo loader/runtime mới phù hợp; class đã định nghĩa trong loader không thể tùy tiện “đổi defining loader” của chính runtime class đó.

### Các công cụ quan sát

Kiểm tra descriptor:

```bash
javap -s -p api.Service
javap -v -p api.Service
```

Thay `api.Service` bằng tên class thật trên class path/module path mà công cụ nhìn thấy. `javap` đọc bytecode và in metadata; nó **không xác nhận** runtime đang dùng định nghĩa từ loader nào.

Quan sát loading của HotSpot JDK 17:

```bash
java -Xlog:class+load=info YourMainClass
```

Đầu ra có thể dài và cách in tùy VM. Log có thể giúp biết class đến từ nguồn nào, nhưng để chứng minh danh tính runtime vẫn cần xét **defining loader** và đường resolve ở chương trình đang chạy.

Với mã có quyền truy cập:

```java
System.out.println(typeA.getName());
System.out.println(typeA.getClassLoader());
System.out.println(typeA == typeB);
```

Đây là đoạn **minh họa**: `typeA`/`typeB` cần là hai giá trị `Class<?>` đã được lấy từ đúng chỗ. Không suy luận từ hai chuỗi `getName()` giống nhau rằng chúng là một `Class<?>`.

## 12. Lỗi phổ biến cần tránh

| Nhầm lẫn | Điều đúng |
|---|---|
| “Hai loader load cùng `Foo` thì JVM luôn ném lỗi.” | Chỉ có xung đột khi ràng buộc liên kết đòi đồng nhất và chúng không thể thỏa. |
| “Cùng tên binary và cùng bytecode tức cùng runtime type.” | Defining loader khác nhau tạo hai runtime class identities khác nhau. |
| “Constraint được tạo cho mọi class name tại thời điểm class file vừa được tìm thấy.” | JVM áp đặt theo hoạt động preparation/resolution được quy định; thời điểm resolution có thể khác nhau. |
| “Có generic `List<Foo>` trong chữ ký là JVM luôn ép các loader dùng chung Foo.” | Descriptor sau erasure có thể chỉ chứa `java.util.List`; generic Signature có ngữ pháp riêng. |
| “Lỗi constraint luôn là `ClassCastException`.” | Vi phạm constraint là lỗi linking/loading dạng `LinkageError`; cast sai xảy ra tại runtime. |
| “Dùng tên class giống nhau trong hai plugin là cách chia sẻ DTO.” | Shared DTO phải dùng chung runtime definition thông qua loader phù hợp. |
| “Dùng parent-first là JVM không còn cần loading constraint.” | Constraint là bảo đảm ở tầng JVM; delegation là chiến lược lookup giúp thỏa nhiều constraint. |
| “Lỗi chỉ có thể xảy ra ngay lúc `new CustomLoader()`.” | Loader object creation khác class linking; lỗi có thể xuất hiện khi nạp, preparation hoặc resolution. |
| “Method descriptor chỉ gồm tham số, không gồm kiểu trả về.” | Method descriptor chứa tham số **và** return type, ví dụ `(LFoo;)LFoo;`. |
| “`LinkageError` nào cũng là loading constraint violation.” | `LinkageError` là nhóm lỗi rộng, cần xem subtype/cause/message và bối cảnh. |

## 13. Bài tập tự kiểm tra

**Câu 1.** Loader A và B cùng định nghĩa `com.example.Event`. Nếu chương trình không giao tiếp nào đòi thống nhất `Event`, việc đó tự động vi phạm loading constraint không?

**Đáp án:** Không. Hai runtime classes cùng tên có thể cùng tồn tại. Constraint chỉ phát sinh ở các tình huống được JVM chỉ định cần type-safe linkage giữa các loader.

**Câu 2.** Method `Event echo(Event input)` được biểu diễn bằng descriptor nào? Nếu hai loader tham gia liên kết method này, tên nào là ứng viên của constraint?

**Đáp án:** Với `Event` thuộc `com.example`, descriptor là `(Lcom/example/Event;)Lcom/example/Event;`. Tên kiểu tham chiếu `com.example.Event` là ứng viên khi JVM áp đặt constraint phù hợp.

**Câu 3.** Hai loader đều gọi `loadClass("java.lang.String")` qua parent delegation và nhận `String.class` của bootstrap. Constraint đòi hai bên thống nhất `String` có thỏa không?

**Đáp án:** Có, vì cùng một runtime class được sử dụng, mặc dù initiating loaders khác nhau.

**Câu 4.** Tại sao không dùng kết quả `clazzA.getName().equals(clazzB.getName())` để chứng minh hai class giống nhau?

**Đáp án:** `getName()` chỉ phản ánh tên, còn runtime identity còn phụ thuộc defining loader. So sánh `clazzA == clazzB` mới xác nhận cùng object `Class` đại diện cùng runtime type.

**Câu 5.** Vì sao `List<Event> fetch()` không nhất thiết áp đặt constraint trực tiếp cho `Event` chỉ từ method descriptor?

**Đáp án:** Generic argument `Event` bị erasure; descriptor JVM thường là `()Ljava/util/List;`. Việc xử lý `Event` ở mã khác vẫn có thể tạo symbolic references/constraints riêng.

**Câu 6.** Một class trong plugin override method dùng `api.Event` được định nghĩa ở loader cha. Cách triển khai nào giúp tránh xung đột?

**Đáp án:** Plugin loader ủy quyền namespace shared API (bao gồm `api.Event`) tới defining loader chung, nhờ vậy cả hai bên resolve cùng một class. Tránh định nghĩa copy `api.Event` bên plugin.

**Câu 7.** Một loading constraint đã được ghi nhận khi một loader chưa load `api.Event`. Loader này sau đó cố định nghĩa bản `api.Event` khác với bên kia. Có thể xảy ra gì?

**Đáp án:** Khi VM ghi nhận initiating loader/class mới và kiểm tra constraints, nếu không thể thỏa quan hệ bình đẳng, hoạt động nạp liên quan thất bại với `LinkageError`. Không cần giả định lỗi chắc chắn nổ ngay ở lần áp đặt constraint trước đó.

## 14. Tóm tắt kiến thức cốt lõi và tham khảo

Loading constraint là **quy tắc bảo toàn tính an toàn kiểu khi linking xuyên class loaders**. JVM có thể cho phép nhiều class cùng binary name tồn tại, nhưng khi các phương thức/field trong mối quan hệ liên kết phải dùng **cùng một kiểu tham chiếu**, VM yêu cầu tên đó resolve thành **cùng runtime class** ở các loader có liên quan.

Nhớ bốn điều:

1. **Class identity** = binary name + defining loader.
2. **Loading constraint** ký hiệu `N^L1 = N^L2`: cùng tên `N` phải chỉ cùng runtime type khi liên kết yêu cầu.
3. JVM áp đặt ràng buộc trong **preparation** (ví dụ override/method selection) và **resolution** (field/method/interface method); vi phạm gây **`LinkageError`** theo quy tắc của JVM.
4. **Shared API types** nên được định nghĩa một lần ở loader chung, để các plugin/caller dùng cùng runtime identity qua delegation thích hợp.

Tài liệu chuẩn:

- [JVMS 17 — `5.3.4` Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): lý do, ký hiệu, thời điểm ghi nhận class và kiểm tra loading constraints.
- [JVMS 17 — `5.4.2` Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2): áp đặt constraint cho phương thức có thể override và phương thức được chọn từ interface.
- [JVMS 17 — `5.4.3` Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3): các rule liên quan symbolic field, method và interface method references.
- [JVMS 17 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): ngữ pháp field/method descriptor.
- [Java SE 17 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass` và định nghĩa class.