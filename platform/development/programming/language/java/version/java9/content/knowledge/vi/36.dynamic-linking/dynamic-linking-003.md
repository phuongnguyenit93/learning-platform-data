# CallSiteDescriptor, Operation và CallSite

Trong liên kết động của Java, ba khái niệm CallSiteDescriptor, Operation và CallSite có quan hệ chặt chẽ nhưng đảm nhiệm ba vai trò khác nhau. Descriptor mô tả một điểm gọi cần được liên kết; Operation diễn đạt thao tác ở mức ngôn ngữ như đọc thuộc tính hoặc gọi hàm; CallSite giữ MethodHandle đích mà JVM sẽ gọi.

Trong hệ sinh thái Dynalink, các kiểu CallSiteDescriptor và Operation thuộc module jdk.dynalink. CallSite nền tảng thuộc java.lang.invoke. Dynalink kết hợp chúng để biến một thao tác động thành MethodHandle phù hợp với đối tượng thực tế, rồi có thể liên kết lại khi kiểu đối tượng thay đổi.

## 1. Bức tranh tổng thể

Giả sử một ngôn ngữ động cho phép viết:

~~~text
value = object.color
~~~

Tại thời điểm biên dịch, kiểu thực tế của object có thể chưa biết. Runtime có thể biểu diễn thao tác này bằng một invokedynamic call site:

~~~text
invokedynamic GET:PROPERTY:color (Object)Object
~~~

Khi lệnh được gọi lần đầu, bootstrap method tạo descriptor và call site rồi giao cho DynamicLinker. Linker tìm một MethodHandle có thể đọc thuộc tính color trên kiểu đối tượng thực tế, gắn điều kiện bảo vệ phù hợp và cài MethodHandle đó làm target.

Ở những lần gọi tiếp theo:

1. Call site chạy target đã liên kết.
2. Guard kiểm tra giả định mà target dựa vào, thường là kiểu receiver hoặc trạng thái liên quan.
3. Nếu guard còn đúng, MethodHandle đích được gọi.
4. Nếu guard sai hoặc linkage bị vô hiệu hóa, call site quay lại cơ chế relink.
5. Linker tạo một GuardedInvocation mới và cập nhật target.

Nhờ vậy một biểu thức nguồn có thể hoạt động với nhiều kiểu đối tượng mà không cần biết trước mọi kiểu ở thời điểm biên dịch.

## 2. Phân biệt ba khái niệm

| Thành phần | Package | Trách nhiệm |
|---|---|---|
| CallSiteDescriptor | jdk.dynalink | Giữ Lookup, Operation và MethodType của điểm gọi |
| Operation | jdk.dynalink | Mô tả thao tác động ở mức ngôn ngữ |
| CallSite | java.lang.invoke | Giữ MethodHandle target và cung cấp dynamicInvoker |
| RelinkableCallSite | jdk.dynalink | Bổ sung giao thức để DynamicLinker thay target khi cần relink |
| DynamicLinker | jdk.dynalink | Điều phối việc tìm linker và cài target cho call site |

Đừng nhầm CallSiteDescriptor với CallSite. Descriptor là dữ liệu mô tả yêu cầu liên kết; CallSite là đối tượng thực thi giữ target MethodHandle.

Cũng đừng nhầm Operation với MethodHandle. Operation nói rằng chương trình muốn làm gì, còn MethodHandle là cách thực hiện cụ thể thao tác đó trên một kiểu đối tượng nhất định.

## 3. CallSiteDescriptor

CallSiteDescriptor thuộc package jdk.dynalink. Constructor chính nhận ba thành phần:

~~~java
new CallSiteDescriptor(lookup, operation, methodType)
~~~

- Lookup: MethodHandles.Lookup của class chứa điểm gọi. Nó mang ngữ cảnh truy cập và quyền tra cứu mà bootstrap được cấp.
- Operation: thao tác động cần thực hiện.
- MethodType: chữ ký của call site, gồm kiểu tham số và kiểu trả về.

Ví dụ:

~~~java
MethodType type = MethodType.methodType(
        Object.class,
        Object.class
);

Operation operation = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");

CallSiteDescriptor descriptor =
        new CallSiteDescriptor(
                MethodHandles.lookup(),
                operation,
                type
        );
~~~

MethodType ở đây có dạng (Object)Object: nhận receiver kiểu Object và trả về Object. Tên thuộc tính color đã được gắn vào NamedOperation nên không cần truyền thêm một đối số tên thuộc tính khi gọi.

### Descriptor là immutable

CallSiteDescriptor được thiết kế bất biến. Khi cần thay đổi operation hoặc MethodType, các phương thức changeOperation và changeMethodType tạo hoặc tìm một descriptor khác:

~~~java
CallSiteDescriptor propertyDescriptor =
        descriptor.changeOperation(
                StandardOperation.GET
                        .withNamespace(StandardNamespace.PROPERTY)
                        .named("title")
        );

CallSiteDescriptor newTypeDescriptor =
        descriptor.changeMethodType(
                MethodType.methodType(
                        String.class,
                        Object.class
                )
        );
~~~

Các biến thể này không sửa descriptor ban đầu. Tính bất biến giúp descriptor an toàn để dùng làm dữ liệu mô tả và khóa so sánh trong quá trình liên kết.

Lookup phải được lấy từ bootstrap method của call site tương ứng. Không thay nó bằng một Lookup có quyền rộng hơn chỉ để làm cho việc liên kết thành công; điều đó có thể mở rộng quyền truy cập ngoài ý muốn.

## 4. Operation mô tả thao tác động

Operation là interface trong jdk.dynalink. Nó không tự thực hiện việc đọc hoặc ghi dữ liệu. Nó mô tả ý định để các linker lựa chọn cách thực hiện.

Java 9 cung cấp StandardOperation với các thao tác cơ bản:

| Operation | Ý nghĩa |
|---|---|
| GET | Đọc giá trị từ một namespace |
| SET | Ghi giá trị vào một namespace |
| CALL | Gọi một đối tượng có thể gọi |
| NEW | Gọi một constructor |

StandardOperation.REMOVE được bổ sung từ Java 10, không phải API có sẵn trong Java 9. Khi viết code cần chạy trên Java 9, không tham chiếu hằng số này.

### NamespaceOperation

GET và SET cần được kết hợp với ít nhất một namespace để xác định loại vùng dữ liệu cần truy cập. StandardNamespace định nghĩa ba namespace chuẩn:

- PROPERTY: thuộc tính của object.
- ELEMENT: phần tử trong collection hoặc cấu trúc tương tự.
- METHOD: method có thể được tra cứu trên object.

Ví dụ:

~~~java
Operation propertyGet =
        StandardOperation.GET.withNamespace(
                StandardNamespace.PROPERTY
        );

Operation elementGet =
        StandardOperation.GET.withNamespace(
                StandardNamespace.ELEMENT
        );

Operation methodGet =
        StandardOperation.GET.withNamespace(
                StandardNamespace.METHOD
        );
~~~

Một ngôn ngữ có thể dùng nhiều namespace trong cùng operation khi cú pháp nguồn cho phép một biểu thức tra cứu nhiều loại thành viên.

### NamedOperation

NamedOperation gắn một tên cố định vào operation:

~~~java
Operation getColor = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");
~~~

Tên color được gắn vào operation và không còn là tham số runtime của call site. Vì vậy chữ ký từ (receiver, name) -> value trở thành (receiver) -> value.

NamedOperation cũng có thể gắn tên chẩn đoán cho CALL hoặc NEW. Trong trường hợp đó, tên giúp mô tả thao tác trong log hoặc thông báo lỗi nhưng không thay đổi chữ ký của call site.

## 5. CallSite trong java.lang.invoke

java.lang.invoke.CallSite là một holder cho MethodHandle được gọi là target. Một invokedynamic instruction sau khi liên kết sẽ ủy quyền các lần gọi cho target hiện tại của CallSite.

Các phương thức quan trọng:

~~~java
MethodType type()
MethodHandle getTarget()
void setTarget(MethodHandle newTarget)
MethodHandle dynamicInvoker()
~~~

type() trả về MethodType cố định của call site. Target có thể được thay đổi ở một số loại call site, nhưng target mới phải có MethodType bằng chính xác MethodType ban đầu. Nếu không, setTarget ném WrongMethodTypeException.

dynamicInvoker() trả về một MethodHandle có cùng kiểu với call site và luôn gọi target hiện tại. Khi target thay đổi, caller vẫn dùng cùng dynamic invoker.

CallSite là lớp abstract do JDK quản lý với ba loại concrete chính: ConstantCallSite, MutableCallSite và VolatileCallSite.

## 6. Ba loại CallSite

| Loại | Target có thay đổi? | Cách nhìn thấy cập nhật |
|---|---|---|
| ConstantCallSite | Không | Target cố định suốt vòng đời |
| MutableCallSite | Có | Tương tự biến thông thường; có thể cần syncAll |
| VolatileCallSite | Có | Target có semantics volatile |

### ConstantCallSite

ConstantCallSite phù hợp khi target đã biết và không cần relink:

~~~java
ConstantCallSite site = new ConstantCallSite(target);
~~~

Target là cố định. Gọi setTarget sẽ ném UnsupportedOperationException. Vì target không đổi, dynamicInvoker có thể trả trực tiếp target cố định.

### MutableCallSite

MutableCallSite phù hợp khi cần thay target nhưng không yêu cầu mỗi thread nhìn thấy cập nhật ngay lập tức:

~~~java
MutableCallSite site = new MutableCallSite(initialTarget);
MethodHandle invoker = site.dynamicInvoker();

site.setTarget(newTarget);
MutableCallSite.syncAll(
        new MutableCallSite[] { site }
);
~~~

setTarget có semantics tương tự ghi vào một biến thông thường. Thread khác có thể tiếp tục dùng target cũ nếu không có đồng bộ thích hợp.

syncAll tạo một điểm đồng bộ để các thread khác chấp nhận target mới trong những lần đọc tiếp theo. Nó không đảo ngược những lần gọi đã bắt đầu bằng target cũ. Việc setTarget và syncAll thường cần được phối hợp dưới một cơ chế loại trừ tương hỗ nếu nhiều thread cùng cập nhật.

syncAll có thể tốn chi phí đáng kể; nên gom nhiều call site vào một lần gọi khi phù hợp.

### VolatileCallSite

VolatileCallSite phù hợp khi thay đổi target phải được quan sát theo semantics volatile:

~~~java
VolatileCallSite site = new VolatileCallSite(initialTarget);
MethodHandle invoker = site.dynamicInvoker();

site.setTarget(newTarget);
~~~

Một lần đọc target tiếp theo phải quan sát cập nhật volatile mới nhất theo Java Memory Model. VolatileCallSite không cần syncAll. Đổi lại, việc đồng bộ chặt chẽ giữa reader và writer có thể làm tăng chi phí so với MutableCallSite.

Chọn loại call site dựa trên tần suất thay đổi target và yêu cầu visibility giữa các thread. Không dùng VolatileCallSite chỉ vì muốn an toàn hơn nếu target thực tế không cần được cập nhật thường xuyên hoặc quan sát tức thời.

## 7. RelinkableCallSite trong Dynalink

Dynalink cần thêm khả năng thay target khi guard không còn đúng. Vì vậy một call site được DynamicLinker quản lý phải triển khai interface RelinkableCallSite.

Interface này cung cấp các thao tác chính:

- initialize: cài MethodHandle ban đầu.
- getDescriptor: trả về CallSiteDescriptor.
- relink: tích hợp GuardedInvocation mới vào target.
- resetAndRelink: bỏ linkage state cũ theo yêu cầu rồi cài linkage mới.

Trong thư viện hỗ trợ, AbstractRelinkableCallSite kế thừa MutableCallSite và triển khai RelinkableCallSite. Vì vậy SimpleRelinkableCallSite và ChainedCallSite vừa là CallSite của java.lang.invoke vừa là call site có thể được Dynalink quản lý.

Hai implementation thường gặp:

- SimpleRelinkableCallSite dùng monomorphic inline cache: giữ một linkage hiện tại và thay nó khi gặp loại receiver khác.
- ChainedCallSite dùng polymorphic inline cache: có thể giữ chuỗi nhiều GuardedInvocation còn hợp lệ để hỗ trợ nhiều loại receiver.

ChainedCallSite có giới hạn độ dài chuỗi và có thể loại bỏ linkage cũ khi vượt giới hạn. Có thể tùy chỉnh giới hạn bằng cách subclass theo API.

## 8. DynamicLinker và quá trình liên kết

DynamicLinker là bộ điều phối chính của Dynalink. Thông thường, runtime tạo một DynamicLinker thông qua DynamicLinkerFactory:

~~~java
DynamicLinker linker =
        new DynamicLinkerFactory().createLinker();
~~~

Bootstrap method tạo CallSiteDescriptor và một RelinkableCallSite, sau đó gọi:

~~~java
CallSite site = linker.link(relinkableCallSite);
~~~

link() cài một MethodHandle ban đầu vào call site để gọi cơ chế relink. Khi call site được gọi lần đầu, linker nhận đối số thực tế và tìm một GuardingDynamicLinker phù hợp.

Với Java object thông thường, DynamicLinkerFactory mặc định cung cấp BeansLinker để áp dụng semantics truy cập bean của Java. Nếu runtime triển khai object model riêng hoặc conversion riêng, có thể đăng ký GuardingDynamicLinker tương ứng.

### GuardedInvocation

Linker thường trả về GuardedInvocation, gồm:

- MethodHandle thực hiện thao tác.
- Guard xác nhận các giả định mà invocation phụ thuộc.
- Có thể có SwitchPoint để vô hiệu hóa linkage khi trạng thái liên quan thay đổi.
- Có thể khai báo exception làm điều kiện invalidation theo hợp đồng API.

Khi guard không còn đúng hoặc SwitchPoint bị invalidate, call site dùng fallback để yêu cầu linker tạo linkage mới. Guard giúp tái sử dụng target nhanh khi giả định còn đúng mà không phải phân tích lại operation ở mọi lần gọi.

## 9. Luồng bootstrap minh họa

Một bootstrap method tối giản có thể làm như sau:

~~~java
private static final DynamicLinker LINKER =
        new DynamicLinkerFactory().createLinker();

static CallSite bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        MethodType type) {

    Operation operation = StandardOperation.GET
            .withNamespace(StandardNamespace.PROPERTY)
            .named(name);

    CallSiteDescriptor descriptor =
            new CallSiteDescriptor(
                    lookup,
                    operation,
                    type
            );

    return LINKER.link(
            new SimpleRelinkableCallSite(descriptor)
    );
}
~~~

Trong bytecode thực tế, JVM gọi bootstrap method khi liên kết invokedynamic instruction. Bootstrap nhận Lookup, tên call site và MethodType. Runtime chuyển tên thành Operation, tạo descriptor rồi trả về một CallSite mà JVM có thể gọi.

Khi không dùng compiler sinh invokedynamic bytecode, chương trình interpreter vẫn có thể tạo CallSite trực tiếp và lưu nó trong biểu diễn AST hoặc cấu trúc thực thi của ngôn ngữ.

## 10. Ví dụ chạy được với Java 17+

Ví dụ dưới đây dùng Dynalink mặc định để đọc thuộc tính color trên ba kiểu Java object khác nhau. Một call site duy nhất được dùng lại. SimpleRelinkableCallSite sẽ liên kết lại khi receiver thay đổi kiểu.

Tạo file **DynalinkCallSiteDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkCallSiteDemo {
    public static class A {
        public String color;

        public A(String color) {
            this.color = color;
        }
    }

    public static class B {
        private final String color;

        public B(String color) {
            this.color = color;
        }

        public String getColor() {
            return color;
        }
    }

    public static class C {
        private final int color;

        public C(int color) {
            this.color = color;
        }

        public int getColor() {
            return color;
        }
    }

    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    static CallSite bootstrap(
            MethodHandles.Lookup lookup,
            String propertyName,
            MethodType type) {

        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named(propertyName);

        CallSiteDescriptor descriptor =
                new CallSiteDescriptor(lookup, operation, type);

        return LINKER.link(
                new SimpleRelinkableCallSite(descriptor)
        );
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(
                Object.class,
                Object.class
        );

        CallSite site = bootstrap(
                MethodHandles.lookup(),
                "color",
                type
        );

        MethodHandle invoker = site.dynamicInvoker();

        System.out.println(invoker.invokeExact((Object) new A("red")));
        System.out.println(invoker.invokeExact((Object) new B("green")));
        System.out.println(invoker.invokeExact((Object) new C(255)));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac DynalinkCallSiteDemo.java
java DynalinkCallSiteDemo
~~~

Kết quả stdout:

~~~text
red
green
255
~~~

Giải thích:

1. Operation mô tả thao tác GET trong namespace PROPERTY và gắn tên color.
2. MethodType quy định call site nhận Object và trả về Object.
3. CallSiteDescriptor giữ Lookup, Operation và MethodType.
4. DynamicLinker tạo linkage đầu tiên cho receiver A.
5. Khi receiver là B rồi C, guard của linkage trước không còn phù hợp; SimpleRelinkableCallSite yêu cầu linker relink.
6. BeansLinker tìm public field hoặc JavaBean getter phù hợp và thích nghi kết quả về Object.

Ví dụ được biên dịch bằng API Java 9 với javac --release 9 và chạy trên JDK 24.0.2. Các class demo được khai báo public để linker mặc định có thể truy cập thành viên công khai.

## 11. Ví dụ cập nhật MutableCallSite

CallSite nền tảng có thể được dùng độc lập với Dynalink để thay target MethodHandle:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle upper = lookup.findVirtual(
        String.class,
        "toUpperCase",
        MethodType.methodType(String.class)
);
MethodHandle lower = lookup.findVirtual(
        String.class,
        "toLowerCase",
        MethodType.methodType(String.class)
);

MutableCallSite site = new MutableCallSite(upper);
MethodHandle invoker = site.dynamicInvoker();

System.out.println((String) invoker.invokeExact("Java"));

site.setTarget(lower);
MutableCallSite.syncAll(
        new MutableCallSite[] { site }
);

System.out.println((String) invoker.invokeExact("Java"));
~~~

Kết quả stdout:

~~~text
JAVA
java
~~~

dynamicInvoker được tạo một lần nhưng mỗi lần gọi đều đi qua target hiện tại. Sau setTarget, syncAll giúp các thread khác chấp nhận target mới theo semantics của MutableCallSite.

## 12. Lỗi thường gặp

**Nhầm CallSiteDescriptor với CallSite:** descriptor là mô tả bất biến; CallSite giữ target MethodHandle có thể được gọi.

**Dùng GET hoặc SET mà không có namespace:** các standard operation này cần NamespaceOperation để xác định property, element hoặc method namespace.

**Quên NamedOperation:** nếu tên thuộc tính cố định, named("color") loại tên khỏi tham số runtime của call site. Nếu không gắn tên, MethodType phải chứa đối số name.

**Dùng sai MethodType:** MethodType của descriptor phải khớp chữ ký call site và mọi target MethodHandle được cài phải có đúng kiểu đó.

**Trả về CallSite thường cho DynamicLinker:** linker cần RelinkableCallSite. Dùng SimpleRelinkableCallSite, ChainedCallSite hoặc implementation tự viết đúng interface.

**Giữ Lookup có quyền quá rộng:** bootstrap nên truyền Lookup được JVM cấp. Không tự thay bằng privileged lookup không cần thiết.

**Giả định target luôn giữ nguyên:** DynamicLinker có thể relink khi guard thất bại hoặc linkage bị invalidate.

**Dùng SimpleRelinkableCallSite cho nhiều receiver mà kỳ vọng giữ mọi cache:** SimpleRelinkableCallSite là monomorphic. Cần cân nhắc ChainedCallSite nếu workload có nhiều kiểu receiver lặp lại.

**Nhầm MutableCallSite với VolatileCallSite:** MutableCallSite không bảo đảm thread khác thấy target mới ngay; VolatileCallSite có volatile semantics.

**Quên syncAll sau cập nhật MutableCallSite:** nếu cần các thread khác chấp nhận target mới, hãy dùng syncAll hoặc một giao thức đồng bộ phù hợp.

**Cố thay target ConstantCallSite:** target của ConstantCallSite không thể thay đổi; setTarget luôn ném UnsupportedOperationException.

## 13. Cách lựa chọn

| Nhu cầu | Lựa chọn |
|---|---|
| Biểu diễn thao tác động như GET property hoặc CALL | Operation |
| Giữ Lookup, operation và chữ ký bootstrap | CallSiteDescriptor |
| Giữ MethodHandle đích cho invokedynamic | CallSite |
| Liên kết và tự relink theo receiver | DynamicLinker + RelinkableCallSite |
| Chỉ cần một linkage hiện tại | SimpleRelinkableCallSite |
| Cache nhiều receiver type | ChainedCallSite |
| Target không bao giờ thay đổi | ConstantCallSite |
| Target thay đổi, chấp nhận đồng bộ theo đợt | MutableCallSite |
| Target thay đổi và cần volatile visibility | VolatileCallSite |

Dynalink phù hợp nhất khi xây dựng runtime cho ngôn ngữ động, interpreter hoặc hệ thống cần dispatch theo kiểu đối tượng tại runtime. Với ứng dụng Java thông thường có kiểu tĩnh, gọi method trực tiếp thường đơn giản hơn.

## 14. Checklist thiết kế

- Phân biệt rõ jdk.dynalink và java.lang.invoke.
- Tạo Operation đúng namespace và tên thao tác.
- Đảm bảo MethodType của descriptor khớp chữ ký invokedynamic.
- Truyền Lookup đúng từ bootstrap method.
- Giữ CallSiteDescriptor bất biến và tạo descriptor mới khi đổi operation/type.
- Dùng RelinkableCallSite khi giao call site cho DynamicLinker.
- Chọn SimpleRelinkableCallSite hoặc ChainedCallSite theo số lượng kiểu receiver thường gặp.
- Kiểm tra guard, SwitchPoint và điều kiện invalidation trong linker tùy chỉnh.
- Giữ MethodType của target ổn định qua mọi lần relink.
- Chọn Constant, Mutable hoặc VolatileCallSite theo semantics cập nhật target và visibility giữa thread.
- Dùng javac --release 9 để kiểm tra code tương thích Java 9; không đưa API được bổ sung ở phiên bản sau vào baseline Java 9.

## Tài liệu tham khảo

- [jdk.dynalink module — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/module-summary.html)
- [DynamicLinker — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html)
- [StandardOperation — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html)
- [CallSite — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/CallSite.html)
- [MutableCallSite — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [ConstantCallSite — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/ConstantCallSite.html)
