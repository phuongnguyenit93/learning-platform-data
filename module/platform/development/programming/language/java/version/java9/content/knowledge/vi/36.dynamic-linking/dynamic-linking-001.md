# Vai trò jdk.dynalink trong ngôn ngữ có kiểu động

## Mục tiêu

- Giải thích vai trò của module \`jdk.dynalink\` trong runtime ngôn ngữ có kiểu động trên JVM.
- Phân biệt Dynalink với \`invokedynamic\` và \`java.lang.invoke\`.
- Mô tả cách call site được liên kết theo kiểu thực tế của receiver.
- Hiểu \`DynamicLinkerFactory\`, \`DynamicLinker\`, \`CallSiteDescriptor\`, \`Operation\` và \`RelinkableCallSite\`.
- Giải thích guard, relinking và inline cache đơn hình/đa hình.
- Dùng linker mặc định để truy cập Java field và JavaBean property.
- Xác định khi nào cần custom \`GuardingDynamicLinker\` và khi nào không cần Dynalink.

## 1. Bài toán mà Dynalink giải quyết

Trong Java thông thường, compiler biết kiểu receiver tại thời điểm biên dịch:

~~~java
String color = car.getColor();
~~~

Compiler tạo lời gọi phù hợp vì kiểu của \`car\` đã được xác định.

Trong một ngôn ngữ có kiểu động, chương trình có thể viết:

~~~text
color = object.color
~~~

Tại thời điểm biên dịch, runtime có thể chưa biết \`object\` thuộc class nào. Khi chạy, nó có thể lần lượt nhận object có public field \`color\`, JavaBean có \`getColor()\`, object theo mô hình riêng của ngôn ngữ hoặc object từ runtime khác.

Runtime cần thực hiện cùng một thao tác ngữ nghĩa — đọc property \`color\` — trên từng object. Nếu tự viết logic reflection và dispatch, runtime phải tự quản lý lookup, method handle, cache, guard, chuyển đổi kiểu và việc liên kết lại khi receiver thay đổi.

\`jdk.dynalink\` cung cấp framework cho phần liên kết động cấp cao này. Runtime biểu diễn thao tác như GET property, SET property, truy cập element hoặc gọi method dưới dạng operation tại call site. Dynalink tìm method handle phù hợp dựa trên đối số thực tế, cài đặt nó vào call site và relink khi điều kiện liên kết không còn đúng.

Dynalink không thay parser, type checker, interpreter, compiler hay bytecode generator. Các thành phần đó vẫn thuộc runtime của ngôn ngữ.

## 2. Dynalink, invokedynamic và MethodHandle

Ba thành phần liên quan nhưng giải quyết các tầng khác nhau:

| Thành phần | Vai trò |
|---|---|
| \`invokedynamic\` | Lệnh bytecode JVM tạo call site được liên kết động qua bootstrap method |
| \`java.lang.invoke\` | API cấp thấp để tạo, kết hợp và gọi \`MethodHandle\`, \`CallSite\` và bootstrap method |
| \`jdk.dynalink\` | Framework cấp cao mô tả operation trên object, chọn linker và quản lý relinking |

\`invokedynamic\` không tự hiểu biểu thức \`object.color\`. Nó tạo điểm gọi động và giao việc thiết lập call site cho bootstrap method.

\`MethodHandle\` biểu diễn lời gọi có kiểu đến method, constructor hoặc thao tác khác. API \`java.lang.invoke\` không tự định nghĩa ngữ nghĩa property, element, method namespace hay quy tắc chuyển đổi kiểu của một ngôn ngữ.

Dynalink bổ sung lớp ngữ nghĩa đó. Runtime mô tả ý định bằng \`Operation\`, rồi để \`DynamicLinker\` tìm method handle thực hiện operation trên receiver hiện tại.

## 3. Module jdk.dynalink

\`jdk.dynalink\` là module JDK có từ Java 9. Các package chính:

| Package | Nội dung |
|---|---|
| \`jdk.dynalink\` | Operation, call site descriptor, dynamic linker và factory |
| \`jdk.dynalink.beans\` | Linker cho Java object thông thường |
| \`jdk.dynalink.linker\` | Interface để runtime triển khai linker và type conversion riêng |
| \`jdk.dynalink.linker.support\` | Lớp hỗ trợ cho custom linker |
| \`jdk.dynalink.support\` | Implementation và tiện ích cho call site |

Với ứng dụng dùng classpath trên JDK có module này, có thể import API trực tiếp. Nếu ứng dụng là named module, khai báo dependency trong \`module-info.java\`:

~~~java
module example.dynamic.runtime {
    requires jdk.dynalink;
}
~~~

Dynalink là API liên kết động, không phải một ngôn ngữ hay script engine. Việc JDK cung cấp module này không đồng nghĩa JDK cung cấp sẵn parser hoặc runtime cho một ngôn ngữ động cụ thể.

## 4. Operation và namespace

Dynalink biểu diễn ý định thao tác bằng \`Operation\`. Các operation chuẩn nằm trong \`StandardOperation\`:

- \`GET\`: đọc property, element hoặc method.
- \`SET\`: ghi property hoặc element.
- \`CALL\`: gọi function hoặc method đã lấy được.
- \`NEW\`: tạo object qua constructor.
- \`REMOVE\`: xóa element khi linker hỗ trợ.

GET/SET cần kết hợp với namespace để chỉ rõ loại thành phần đang truy cập:

| Namespace | Ý nghĩa |
|---|---|
| \`PROPERTY\` | Property của object |
| \`ELEMENT\` | Phần tử array, List, Map hoặc object model tương ứng |
| \`METHOD\` | Method được lấy ra để gọi |

Ví dụ, biểu thức đọc property \`color\` được biểu diễn như sau:

~~~java
Operation operation = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");
~~~

\`named("color")\` tạo một \`NamedOperation\`, gắn tên property vào operation. Call site mô tả GET property có tên \`color\`.

Một ngôn ngữ có thể định nghĩa quy tắc phân giải riêng. Cú pháp \`object.name\` có thể thử property trước, rồi mới thử method hoặc namespace khác. Dynalink hỗ trợ \`NamespaceOperation\` để mô tả thao tác liên quan đến nhiều namespace.

## 5. CallSiteDescriptor và RelinkableCallSite

\`CallSiteDescriptor\` lưu thông tin cần thiết để linker xử lý và relink:

1. \`MethodHandles.Lookup\`: lookup của class chứa call site, dùng cho quyền truy cập.
2. \`Operation\`: thao tác động cần thực hiện.
3. \`MethodType\`: kiểu tham số và kiểu trả về của call site.

Ví dụ, property getter nhận receiver kiểu \`Object\` và trả về \`Object\`:

~~~java
MethodType type = MethodType.methodType(
        Object.class, Object.class);
~~~

Dynalink quản lý các call site triển khai \`RelinkableCallSite\`. Hai implementation có sẵn:

- \`SimpleRelinkableCallSite\`: giữ linkage gần nhất, thường gọi là monomorphic inline cache.
- \`ChainedCallSite\`: giữ nhiều linkage cho các kiểu receiver khác nhau, thường gọi là polymorphic inline cache.

Lựa chọn call site ảnh hưởng đến cache khi một điểm gọi nhận nhiều loại receiver. Không có lựa chọn tối ưu cho mọi workload; runtime nên đo trên phân bố kiểu dữ liệu thực tế.

## 6. DynamicLinkerFactory và DynamicLinker

\`DynamicLinkerFactory\` cấu hình và tạo \`DynamicLinker\`:

~~~java
DynamicLinkerFactory factory = new DynamicLinkerFactory();
DynamicLinker linker = factory.createLinker();
~~~

Các cấu hình thường dùng:

- \`setPrioritizedLinkers(...)\`: linker của ngôn ngữ hiện tại được hỏi trước.
- \`setFallbackLinkers(...)\`: linker dự phòng được hỏi sau.
- \`setClassLoader(...)\`: class loader dùng để tìm linker exporter qua ServiceLoader.
- \`setPrelinkTransformer(...)\`: biến đổi guarded invocation trước khi cài vào call site.
- \`setSyncOnRelink(...)\`: cấu hình đồng bộ MutableCallSite sau khi relink.

Nếu không thay đổi fallback mặc định, factory tạo linker có \`BeansLinker\` làm fallback cho Java object thông thường.

Sau khi tạo call site descriptor, runtime gọi:

~~~java
CallSite linked = linker.link(relinkableCallSite);
~~~

\`DynamicLinker.link()\` cài cơ chế relink vào call site. Khi call site được gọi với đối số thực tế, Dynalink tìm linker xử lý được operation và receiver, sau đó cài target method handle phù hợp.

## 7. Guard, method handle và relinking

Một linkage thường gồm hai phần:

- **Target method handle:** thao tác thực tế, ví dụ đọc public field hoặc gọi getter.
- **Guard:** điều kiện để target còn hợp lệ, ví dụ receiver phải thuộc một kiểu hoặc thỏa điều kiện cụ thể.

Linker có thể trả về \`GuardedInvocation\`, đại diện cho method handle có điều kiện.

Luồng xử lý khái quát:

1. Call site được gọi lần đầu và chưa có target phù hợp.
2. Cơ chế relink nhận đối số thực tế và tạo \`LinkRequest\`.
3. Các \`GuardingDynamicLinker\` được hỏi để tìm implementation.
4. Linker phù hợp trả về \`GuardedInvocation\`.
5. Dynalink cài target và guard vào call site.
6. Lần gọi sau có receiver thỏa guard sẽ đi vào target đã liên kết.
7. Nếu receiver mới không thỏa guard, call site được relink để tìm target khác.

Cùng biểu thức \`object.color\` có thể liên kết lần lượt với public field của class A và getter của class B. Runtime không cần tạo hai biểu thức nguồn khác nhau.

Guard giúp tái sử dụng linkage khi điều kiện còn đúng. Relinking giúp call site thích nghi khi kiểu hoặc đặc điểm receiver thay đổi.

## 8. BeansLinker và Java object

\`DynamicLinkerFactory\` mặc định cung cấp \`BeansLinker\` làm fallback. Nhờ đó, runtime có thể truy cập Java object thông thường mà chưa cần custom linker cho mọi class.

Các khả năng chính:

- Public field được biểu diễn như property.
- Public \`getXxx()\`, \`isXxx()\` và \`setXxx()\` được biểu diễn như getter/setter property.
- Record component accessor được biểu diễn như property getter.
- Java array, \`List\` và \`Map\` được truy cập qua element namespace.
- Collection, Map và array có property \`length\` theo quy tắc của linker.
- Method có thể được lấy qua method namespace rồi gọi bằng CALL.
- Constructor có thể được gọi qua NEW khi dùng biểu diễn \`StaticClass\` tương ứng.

BeansLinker dùng quy tắc Java thông thường. Nếu object model của ngôn ngữ có quy tắc khác — ví dụ prototype, dynamic conversion hoặc dispatch nhiều đối số — runtime cần cung cấp linker riêng.

## 9. Ví dụ chạy được: một property trên hai kiểu Java object

Ví dụ tạo call site GET property \`color\`. Call site đầu tiên đọc public field trên \`FieldObject\`, sau đó nhận \`BeanObject\` có private field và public getter. Cùng call site được Dynalink relink cho receiver thứ hai.

Tạo file **DynalinkPropertyDemo.java**:

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

public class DynalinkPropertyDemo {

    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    public static class FieldObject {
        public String color;

        public FieldObject(String color) {
            this.color = color;
        }
    }

    public static class BeanObject {
        private final String color;

        public BeanObject(String color) {
            this.color = color;
        }

        public String getColor() {
            return color;
        }
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup lookup,
            String propertyName,
            MethodType callSiteType) {

        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named(propertyName);

        CallSiteDescriptor descriptor =
                new CallSiteDescriptor(lookup, operation, callSiteType);

        return LINKER.link(new SimpleRelinkableCallSite(descriptor));
    }

    public static void main(String[] args) throws Throwable {
        MethodType type =
                MethodType.methodType(Object.class, Object.class);

        MethodHandle getter = bootstrap(
                MethodHandles.lookup(), "color", type).dynamicInvoker();

        Object first = (Object) getter.invokeExact(
                (Object) new FieldObject("red"));

        Object second = (Object) getter.invokeExact(
                (Object) new BeanObject("green"));

        System.out.println("field-backed property = " + first);
        System.out.println("bean-backed property = " + second);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out DynalinkPropertyDemo.java
java -cp out DynalinkPropertyDemo
~~~

Output chính xác:

~~~text
field-backed property = red
bean-backed property = green
~~~

Ở lần gọi đầu, BeansLinker liên kết operation với public field \`FieldObject.color\`. Khi cùng call site nhận \`BeanObject\`, guard của linkage trước không còn phù hợp và Dynalink relink operation sang \`BeanObject.getColor()\`.

Ví dụ gọi bootstrap method trực tiếp để quan sát call site trong một chương trình Java thông thường. Trong runtime biên dịch ngôn ngữ động thành bytecode, JVM gọi bootstrap method này khi liên kết lệnh \`invokedynamic\`. Dynalink không tự sinh bytecode cho compiler.

Ví dụ tương thích Java 9 trở lên. Có thể kiểm tra API nền tảng bằng lệnh:

~~~bash
javac --release 9 -Xlint:all -d out9 DynalinkPropertyDemo.java
~~~

## 10. Khi nào cần custom GuardingDynamicLinker?

Nếu ngôn ngữ có object model riêng, BeansLinker có thể không đủ. Runtime có thể triển khai \`GuardingDynamicLinker\` hoặc \`TypeBasedGuardingDynamicLinker\`.

Một custom linker thường cần:

- Nhận \`LinkRequest\` để biết operation, call site và đối số hiện tại.
- Xác định object có thuộc object model mà linker quản lý hay không.
- Tạo method handle thực hiện operation.
- Tạo guard mô tả khi nào method handle còn hợp lệ.
- Trả về \`GuardedInvocation\`, hoặc báo không xử lý operation để linker tiếp theo thử.
- Dùng \`LinkerServices\` khi cần chuyển đổi kiểu hoặc phối hợp method handle.

Runtime có thể cấu hình linker của ngôn ngữ mình là prioritized linker. Fallback linker xử lý operation mà linker chính không nhận diện hoặc đưa ra lỗi phù hợp với ngôn ngữ.

Nếu nhiều runtime ngôn ngữ cần interoperability, runtime có thể xuất linker qua \`GuardingDynamicLinkerExporter\`. \`DynamicLinkerFactory\` dùng ServiceLoader và class loader đã cấu hình để tìm exporter. Object từ runtime B khi được truyền vào code runtime A có thể được linker của B giải thích.

## 11. Dynalink không làm thay runtime ngôn ngữ

Dynalink giải quyết liên kết operation với method handle. Runtime vẫn phải tự quyết định:

- Cú pháp và ý nghĩa của biểu thức nguồn.
- Khi nào truy cập là property, element hay method.
- Quy tắc tìm kiếm tên và xử lý property không tồn tại.
- Quy tắc chuyển đổi kiểu và dispatch overload.
- Cách biểu diễn object, function, class và module của ngôn ngữ.
- Cách tạo bytecode hoặc cách interpreter gọi call site.
- Cách báo lỗi cho người viết chương trình bằng ngôn ngữ đó.

Một language runtime có thể dùng Dynalink cùng parser, AST, compiler, interpreter, \`MethodHandle\` và cấu trúc dữ liệu riêng. Dynalink là thành phần liên kết động trong kiến trúc đó.

## 12. Khi nào nên dùng Dynalink?

Dynalink phù hợp khi:

- Xây dựng ngôn ngữ hoặc DSL trên JVM cần truy cập object có kiểu chỉ xác định lúc runtime.
- Một biểu thức nguồn có thể hoạt động trên nhiều loại receiver.
- Cần cache method handle và relink call site khi kiểu thực tế thay đổi.
- Cần interoperability giữa object model riêng và Java object.
- Cần operation property, element, method hoặc constructor thống nhất.

Dynalink thường không cần thiết khi:

- Ứng dụng Java đã biết kiểu receiver tại compile time.
- Chỉ cần gọi method cố định hoặc đọc field đã biết.
- Chỉ cần một lần reflection đơn giản.
- Không có dynamic dispatch, custom object model hoặc yêu cầu relinking.

Dùng Dynalink khi lợi ích từ mô hình call site và linker đáng với độ phức tạp của runtime.

## 13. Lỗi thường gặp

### Nhầm Dynalink với invokedynamic

\`invokedynamic\` là bytecode call site; Dynalink là framework có thể quản lý call site đó. JVM không tự áp đặt operation property hay element.

### Nghĩ Dynalink là một ngôn ngữ hoặc script engine

Dynalink không cung cấp cú pháp, parser, interpreter hay compiler. Runtime ngôn ngữ phải xây dựng những thành phần đó.

### Chỉ dùng Java reflection rồi tự dispatch mọi lần gọi

Reflection đủ cho một thao tác đơn giản, nhưng runtime lớn còn cần guard, cache, relink, type conversion và phối hợp nhiều object model. Dynalink cung cấp abstraction cho phần liên kết này.

### Nghĩ một call site chỉ gắn với một class mãi mãi

Receiver có thể đổi kiểu. Guard không phù hợp khiến call site relink. Cần chọn inline cache phù hợp với số lượng kiểu thường gặp.

### Chọn SimpleRelinkableCallSite cho workload đa hình mà không đo

SimpleRelinkableCallSite chỉ giữ linkage gần nhất. ChainedCallSite có thể giữ nhiều linkage. Hãy đo phân bố receiver và hiệu năng thực tế.

### Bỏ qua MethodType

Target method handle phải tương thích với kiểu call site. Sai kiểu tham số hoặc kiểu trả về có thể làm linkage thất bại hoặc cần chuyển đổi qua LinkerServices.

### Cho rằng BeansLinker hiểu object model riêng

BeansLinker áp dụng semantics Java. Object model khác cần custom GuardingDynamicLinker và quy tắc chuyển đổi tương ứng.

### Cho rằng Dynalink tự tạo bytecode

Dynalink quản lý linking của call site. Compiler vẫn phải tạo class và lệnh \`invokedynamic\`, trừ khi runtime chủ động tạo call site trong interpreter.

## 14. Checklist

- [ ] Đã phân biệt \`invokedynamic\`, \`MethodHandle\` và Dynalink.
- [ ] Đã hiểu module \`jdk.dynalink\` có từ Java 9.
- [ ] Đã biểu diễn thao tác bằng Operation, Namespace và NamedOperation.
- [ ] Đã hiểu vai trò của CallSiteDescriptor và RelinkableCallSite.
- [ ] Đã hiểu DynamicLinkerFactory và DynamicLinker.
- [ ] Đã hiểu GuardedInvocation, guard và relinking.
- [ ] Đã phân biệt SimpleRelinkableCallSite với ChainedCallSite.
- [ ] Đã biết BeansLinker hỗ trợ Java field, JavaBean property và collection element.
- [ ] Đã xác định khi nào cần custom GuardingDynamicLinker.
- [ ] Đã kiểm tra interoperability qua linker exporter nếu kiến trúc cần.
- [ ] Đã biên dịch và chạy ví dụ với Java 9+.

## 15. Tài liệu tham khảo

- [Java SE 24 API: Module jdk.dynalink](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/module-summary.html)
- [Java SE 24 API: DynamicLinker](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html)
- [Java SE 24 API: DynamicLinkerFactory](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html)
- [Java SE 24 API: BeansLinker](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html)

