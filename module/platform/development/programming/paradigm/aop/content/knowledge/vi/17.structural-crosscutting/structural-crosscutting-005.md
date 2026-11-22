# Thay đổi quan hệ kiểu và ảnh hưởng tới mã sử dụng trong AOP

## 1. Từ advice hành vi đến structural crosscutting

**Aspect-Oriented Programming (AOP)** không chỉ có thể bổ sung hành vi trước/sau/bao quanh một **join point** bằng **advice**, mà trong một số ngôn ngữ còn có **structural crosscutting**: thay đổi cấu trúc của kiểu dữ liệu hoặc ràng buộc mối quan hệ giữa các kiểu.

Những khả năng có thể được hỗ trợ, tùy ngôn ngữ và weaver:

- **Inter-type method introduction:** thêm method vào một type mà không sửa source khai báo gốc.
- **Inter-type field introduction:** thêm field/state vào type.
- **Interface introduction:** làm một class thực hiện một interface/capability bổ sung.
- **Parent declaration:** thay đổi quan hệ superclass/interface trong phạm vi ngôn ngữ cho phép.
- **Structural rules:** khai báo ràng buộc hoặc báo lỗi khi cấu trúc vi phạm quy tắc.
- **Mixins/roles:** ghép một tập behavior vào đối tượng hoặc kiểu theo hợp đồng rõ ràng.

Ví dụ ý tưởng:

~~~text
Trước structural weaving:
  Invoice implements DomainEntity

Sau structural weaving:
  Invoice implements DomainEntity, Auditable
~~~

Nếu một weaver thực sự tạo class binary với interface bổ sung trước khi JVM định nghĩa class, những **Invoice instances** của class ấy có thể tương thích với Auditable trong runtime type hierarchy. Điều này có thể ảnh hưởng trực tiếp tới **instanceof, casts, assignments, method dispatch, reflection, generics, serialization và pointcuts dựa vào type hierarchy**.

Điểm quan trọng nhất của chủ đề: **không phải mọi “introduction” đều thay đổi class gốc**. Một số cơ chế tạo proxy hoặc adapter implement interface bổ sung; target bên trong vẫn giữ class ban đầu. Hai cơ chế có hệ quả rất khác với mã sử dụng.

Bài học trình bày AOP cơ bản và nâng cao ở mức tổng quát; không giả định mọi engine hỗ trợ cùng dạng structural weaving.

## 2. Những khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Advice** | Code bổ sung được kích hoạt tại join point phù hợp |
| **Pointcut** | Quy tắc lựa chọn join point |
| **Interception** | Chặn hoặc bao một operation khi thực thi |
| **Structural crosscutting** | Thay đổi hoặc ràng buộc cấu trúc type/member |
| **Inter-type declaration (ITD)** | Khai báo một member hoặc quan hệ kiểu từ aspect áp sang target type |
| **Declare parents** | Một kiểu khai báo quan hệ parent/interface trong một số AOP languages |
| **Introduction** | Bổ sung capability/member/interface |
| **Mixin** | Kết hợp role/behavior vào đối tượng hoặc kiểu |
| **Weaver** | Thành phần ghép các aspects vào chương trình |
| **Static type** | Kiểu compiler gán cho expression |
| **Runtime class** | Class thực tế của object |
| **Subtype** | Quan hệ có thể thay thế một type bằng type khác theo hệ thống kiểu |

**Interception không tự tạo subtype.** Chạy logging advice trước Invoice.save không tự khiến Invoice implement Auditable. Muốn object có quan hệ type mới phải có một **mechanism thay type metadata hoặc tạo object khác hỗ trợ type đó**.

### 2.1. Interface khác superclass

Java hỗ trợ một class extends một superclass trực tiếp và có thể implements nhiều interfaces. Không được đọc “thay đổi quan hệ kiểu” thành “cho phép multiple class inheritance”.

Một số structural changes có thể không thực hiện được vì constraints của class hierarchy, final/sealed declarations, conflicts, module accessibility hoặc bytecode verification.

## 3. Ba mô hình cần vẽ riêng

### 3.1. Binary structural weaving

~~~text
Core class definition
        |
        v
Weaver adds interface/member declarations
        |
        v
Woven class binary
        |
        v
JVM loads class with new type structure
~~~

Nếu thành công, cùng object Core có thể thực hiện interface mới. Reflection trên woven Core class có thể thấy introduced members/interfaces theo dạng binary được tạo.

Cần kiểm tra rằng **consumer compiler** có đủ thông tin type khi compile source gọi introduced method, và runtime dùng binary đã weave tương thích. Không phải class đã load xong cũng được thay arbitrary interfaces trong JVM.

### 3.2. Proxy/adapter tạo object khác

~~~text
Caller --> Adapter P implements Worker, Tagged
                       |
                       v
              Target T implements Worker
~~~

Trong mô hình này:

- P instanceof Tagged: true.
- T instanceof Tagged: false.
- P == T: false nếu là hai allocations riêng.
- P.work có thể delegate tới T.work để cho cùng kết quả.
- Reflection trên class P khác class T.
- Nếu caller cầm raw T, cast Tagged có thể throw.

Adapter có thể bổ sung capability **ở một API boundary**, không phải biến class gốc thành subtype mới.

### 3.3. Subclass-based proxy

Một generated subclass có thể extends target concrete type và implements thêm interface. Proxy P có thể instanceof Core, nhưng nếu target T riêng được giữ để delegate, **P và T vẫn không phải cùng reference**.

Final class không được subclass theo Java rules. Một công cụ sửa binary trực tiếp trước load có các constraints khác; không dùng quy tắc của subclassing để kết luận về mọi loại weaving.

### 3.4. Câu hỏi kiểm chứng mechanism

- Một class definition thực sự đổi hierarchy hay một wrapper mới được tạo?
- Object nào được trao cho caller, P hay T?
- Runtime Class nào implement interface?
- Có type weaving ở compile time/load time không?
- Một loaded class có được instrument theo phạm vi này không?
- Cần recompile consumers để thấy introduced APIs không?
- Direct target calls có đi qua interception/role mới không?

## 4. Interface introduction thay đổi nghĩa vụ hợp đồng

Ví dụ:

~~~java
interface Auditable {
    String auditId();
}
~~~

Một target class không implements Auditable:

~~~java
final class Invoice {
    private final String id;
    Invoice(String id) { this.id = id; }
}
~~~

Đây là hai snippets minh họa, chưa phải chương trình độc lập.

Nếu một AOP language bổ sung Auditable thật sự vào Invoice, **phải có một implementation thích hợp cho auditId**, hoặc compiler/weaver phải áp quy tắc hợp lệ của nó với abstract/default methods.

Hợp đồng interface không chỉ là chữ ký:

- auditId có được phép null không?
- Có ổn định sau khi lưu entity không?
- Có phải duy nhất trong một domain không?
- Có được phép throw ở trạng thái chưa được persistence không?
- Có thread-safe không?
- Có lộ dữ liệu nhạy cảm không?

Một introduced method trả string hằng để lấp đủ chữ ký vẫn có thể phá **behavioral subtyping** nếu interface hứa unique IDs. Type compatibility phải đi kèm semantic compatibility.

### 4.1. Marker interfaces cũng làm thay behavior

Ngay cả interface không có methods có thể ảnh hưởng instanceof, type-based dispatch, reflection, object classification và serialization. Do đó “chỉ thêm marker” không có nghĩa không có tác động lên mã sử dụng.

## 5. Inter-type declaration và declare parents

Một ví dụ **minh họa cú pháp kiểu AspectJ**, không biên dịch bằng javac thuần:

~~~aspectj
public aspect AuditingRole {
    declare parents: demo.Invoice implements demo.Auditable;

    public String demo.Invoice.auditId() {
        return "invoice-audit";
    }
}
~~~

Ý tưởng của đoạn mã:

1. Một aspect xác định target type Invoice.
2. Khai báo Invoice sẽ implement Auditable.
3. Giới thiệu member auditId để đáp ứng contract.
4. Weaver kiểm tra các constraints và tạo type representation tương ứng.
5. Consumers sử dụng woven type theo quy tắc compilation và classloading của môi trường.

Đây là **cú pháp định hướng ý tưởng**, cần xác minh package declarations, syntax và constraints của compiler AOP cụ thể khi ứng dụng. Java compiler thông thường không hiểu aspect declaration.

### 5.1. Giới thiệu field

Một aspect có thể muốn bổ sung state:

~~~text
Invoice:
  introduced auditVersion
  introduced getAuditVersion()
  introduced updateAuditVersion()
~~~

Nhưng field ở đâu? Có thể là per-object binary field, field trong adapter, hoặc external map keyed by identity, tùy implementation. Mỗi phương án có serialization, concurrency, lifecycle và equality khác nhau.

### 5.2. Scope của introduction pattern

Nếu type pattern match cả một package, tất cả classes phù hợp có thể bị thêm interface. Điều này tạo ảnh hưởng dây chuyền:

- Registry coi nhiều objects là Auditable hơn trước.
- Aspect khác chọn các join points theo interface đó.
- Compiler recompile source có overload ambiguities.
- Serializers có thể chọn logic khác cho những type mới.
- Unit tests chỉ một Invoice không phát hiện tác động lên class khác.

Chọn type pattern hẹp và test cả **negative targets** không nên bị introduction.

## 6. Static type, runtime type, instanceof và cast

Trong Java:

- **Static type** xác định methods compiler cho phép gọi và overload signatures có thể chọn.
- **Runtime type** xác định object thực tế có thuộc một interface/class hay không.
- **instanceof** kiểm tra object thực sự compatible với runtime type test.
- **cast** cho phép truy cập contract đã được xác minh nhưng có thể throw ClassCastException nếu sai.
- **Class.isAssignableFrom** và reflection cho biết quan hệ ở class metadata.

Một caller có:

~~~java
Worker worker = obtainWorker();
worker.work();
if (worker instanceof Tagged tagged) {
    System.out.println(tagged.tag());
}
~~~

Đây là snippet chưa độc lập vì cần Worker, Tagged và obtainWorker. Nó cho thấy worker có static type Worker; các methods riêng của Tagged chỉ được gọi khi compiler biết Tagged contract và runtime object phù hợp.

### 6.1. Adapter khác original target

Nếu obtainWorker() trả TaggedAdapter thì instanceof Tagged true. Nếu trả raw CoreWorker chưa implement Tagged thì false. Một API phải nêu rõ liệu mọi Worker nó cấp đều có capability đó hay không.

### 6.2. Binary đã weave nhưng source compiler chưa thấy

Ngay cả khi runtime class thực sự implement interface, một **biến được khai báo Worker** vẫn không tự có method Tagged trong Worker interface. Phải dùng static type/cast/type narrowing phù hợp. Muốn gọi trực tiếp qua concrete type thì compilation phải dùng type information nhất quán với weaving.

## 7. Ví dụ Java 17 runnable: thêm interface bằng adapter, không sửa target class

Ví dụ chạy bằng **JDK 17 thuần**, có chủ đích **không dùng AOP weaver**. Nó làm rõ sự khác nhau giữa object có capability bổ sung và class gốc không đổi, cũng như ảnh hưởng tới overload, generics và reflection.

Tạo **TypeRelationshipDemo.java**:

~~~java
import java.util.List;

public class TypeRelationshipDemo {
    interface Worker {
        String work();
    }

    interface Tagged {
        String tag();
    }

    static final class CoreWorker implements Worker {
        @Override
        public String work() {
            return "core-work";
        }
    }

    static final class TaggedAdapter implements Worker, Tagged {
        private final Worker delegate;
        private final String label;

        TaggedAdapter(Worker delegate, String label) {
            this.delegate = delegate;
            this.label = label;
        }

        @Override
        public String work() {
            return delegate.work();
        }

        @Override
        public String tag() {
            return label;
        }
    }

    static String route(Worker worker) {
        return "Worker";
    }

    static String route(Tagged tagged) {
        return "Tagged";
    }

    static String route(Object value) {
        return "Object";
    }

    static void printTypes(Worker worker, String name) {
        System.out.println(name + " instanceof Worker=" + (worker instanceof Worker));
        System.out.println(name + " instanceof Tagged=" + (worker instanceof Tagged));
    }

    public static void main(String[] args) {
        Worker core = new CoreWorker();
        Worker adapted = new TaggedAdapter(core, "audit");

        printTypes(core, "core");
        printTypes(adapted, "adapted");
        System.out.println("adapted==core=" + (adapted == core));
        System.out.println("core.work=" + core.work());
        System.out.println("adapted.work=" + adapted.work());

        if (adapted instanceof Tagged taggable) {
            System.out.println("adapted.tag=" + taggable.tag());
            System.out.println("route((Tagged)adapted)=" + route(taggable));
        }

        System.out.println("route(adapted)=" + route(adapted));
        System.out.println("route((Object)adapted)=" + route((Object) adapted));

        List<Worker> workers = List.of(adapted);
        System.out.println("workers.element.tag=" + ((Tagged) workers.get(0)).tag());
        System.out.println("Tagged.assignable.from.CoreWorker="
                + Tagged.class.isAssignableFrom(CoreWorker.class));
        System.out.println("Tagged.assignable.from.TaggedAdapter="
                + Tagged.class.isAssignableFrom(TaggedAdapter.class));

        try {
            Tagged invalid = (Tagged) core;
            System.out.println(invalid.tag());
        } catch (ClassCastException error) {
            System.out.println("core.cast=ClassCastException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 TypeRelationshipDemo.java
java TypeRelationshipDemo
~~~

**Stdout thực tế đã được xác minh:**

~~~text
core instanceof Worker=true
core instanceof Tagged=false
adapted instanceof Worker=true
adapted instanceof Tagged=true
adapted==core=false
core.work=core-work
adapted.work=core-work
adapted.tag=audit
route((Tagged)adapted)=Tagged
route(adapted)=Worker
route((Object)adapted)=Object
workers.element.tag=audit
Tagged.assignable.from.CoreWorker=false
Tagged.assignable.from.TaggedAdapter=true
core.cast=ClassCastException
~~~

### 7.1. Hai kết quả work giống nhau nhưng objects khác nhau

TaggedAdapter.work chuyển tiếp tới CoreWorker.work, nên cùng trả core-work. Nhưng adapted==core false: wrapper P và target T khác reference identity.

### 7.2. Chỉ adapter có Tagged

TaggedAdapter implement Worker và Tagged; CoreWorker implement Worker. Vì vậy cast Tagged trên adapted hợp lệ, cast trên raw core throw. **Đây không phải bytecode-level structural weaving của CoreWorker.**

### 7.3. Overload resolution phụ thuộc static expression type

Biến adapted có static type Worker, vì vậy route(adapted) chọn route(Worker) dù runtime object cũng implement Tagged.

Biến taggable có static type Tagged nên route(taggable) chọn route(Tagged). Cast sang Object chọn route(Object).

**Overload resolution là compile-time**, khác virtual method dispatch chọn implementation override trên runtime receiver.

### 7.4. List<Worker> không phải List<Tagged>

Dù element runtime là TaggedAdapter, workers.get(0) có static type Worker. Code phải cast hoặc type-test trước khi gọi Tagged API. Việc bổ sung interface không xóa các quy tắc generics của Java.

### 7.5. Reflection kiểm tra class-level capability

Tagged.class.isAssignableFrom(CoreWorker.class) false nhưng với TaggedAdapter.class là true. Một binary thật đã structural-weave CoreWorker để implement Tagged có thể cho kết quả khác; phải test đúng deployed artifact.

## 8. Thay đổi overload resolution ở mã nguồn

Giả sử chương trình có hai overload:

~~~java
void inspect(Worker worker) { /* ... */ }
void inspect(Tagged tagged) { /* ... */ }
~~~

Đây là snippets minh họa, chưa là chương trình độc lập. Với một expression static type Worker, compiler chọn overload Worker; static type Tagged chọn Tagged.

Nếu một concrete class được introduction để implements đồng thời Worker và Tagged, khi recompile:

~~~java
inspect(concreteValue);
~~~

có thể trở thành **ambiguous** nếu hai overload nhận unrelated interfaces và không cái nào more specific. Phải cast rõ, hoặc thiết kế API không ambiguous.

### 8.1. Runtime object khác compile-time choice

Một thay đổi type hierarchy ở runtime **không tự viết lại method descriptor** của call đã được compile từ trước. Bytecode cũ vẫn nhắm một overload đã chọn, trong khi source recompile với type relation mới có thể chọn khác hoặc báo ambiguous.

Đây là ví dụ vì sao **source compatibility và binary compatibility phải được xét riêng**.

### 8.2. Override khác overload

Override là triển khai một method theo inheritance/dispatch rules; overload là nhiều chữ ký cùng tên. Interface introduction có thể ảnh hưởng cả method set và subtype relations, nhưng theo hai cơ chế khác nhau.

Không dùng tên gọi “match method” để trộn lẫn chọn overload lúc compile với chọn implementation lúc runtime.

## 9. Default methods, xung đột và hierarchy restrictions

Interface có thể có default method:

~~~java
interface A {
    default String label() { return "A"; }
}

interface B {
    default String label() { return "B"; }
}
~~~

Một class implements cả A và B mà chưa có một implementation giải quyết conflict có thể gặp lỗi. Structural introduction không được bỏ qua Java method resolution rules.

### 9.1. Class method và interface defaults

Một concrete/inherited class method có thể có precedence đối với interface default trong những tình huống hợp lệ. Nhưng nếu target method có return type, access hoặc final/static modifier không tương thích với contract, introduction có thể không hợp lệ.

### 9.2. Java không có multiple concrete superclass inheritance

Một declare parents yêu cầu một class extends hai concrete parents là không phù hợp Java type system. Ngay cả thay một superclass cũng có constructor/inherited member constraints.

### 9.3. Final, record và sealed types

Một final class không thể bị subclass. Record classes là final. Sealed types giới hạn permitted subclasses/implementers.

Điều này ảnh hưởng thiết kế generated subclass proxies. Với **direct binary weaving**, một công cụ có thể có khả năng khác, nhưng vẫn phải đáp ứng type rules, class verifier và constraints phù hợp. Không khẳng định một final class cấm mọi dạng interface introduction; cũng không khẳng định weaver luôn bỏ qua được sealed hierarchy.

## 10. Generics, erasure và contracts

Một interface generic:

~~~java
interface Container<T> {
    T get();
}
~~~

Nếu một Invoice type thực sự implement Container<Invoice>, compiler có thể dùng generic contract ấy. Nhưng Java generics sử dụng **type erasure** ở runtime; instanceof không xác minh tùy ý tất cả generic type arguments.

### 10.1. Invariance

Ngay cả khi Invoice là subtype của Auditable, List<Invoice> không tự là subtype của List<Auditable>. Nếu API chỉ đọc, wildcard có thể phù hợp:

~~~java
List<? extends Auditable> view = invoices;
~~~

Dòng này chỉ hợp lệ nếu invoices có compile-time type phù hợp và Invoice là Auditable theo type system compiler dùng.

### 10.2. Bridge methods và name clashes

Một generic interface method có thể cần bridge method hoặc gây name-clash sau erasure. Nếu method đã tồn tại trên target có signature không tương thích với introduced generic contract, compiler/weaver phải xử lý hợp lệ hoặc từ chối.

Không suy introduction đúng chỉ từ hình thức khai báo source của các generic parameters.

### 10.3. Raw interface không chứng minh type argument đúng

Một object runtime có thể cast được sang raw Container, nhưng nếu implementation trả dữ liệu khác với Container<Invoice> contract, ClassCastException có thể xảy ra tại use site. Generic contract là phần cần kiểm thử, không phải annotation trang trí.

## 11. Reflection, annotations và metadata

Structural type changes có thể ảnh hưởng:

- Class.getInterfaces()/getGenericInterfaces().
- Class.isAssignableFrom().
- Class.getMethods()/getDeclaredMethods().
- Method.getDeclaringClass().
- Method/Type annotations và generic metadata.
- Object.getClass().
- Framework-neutral scanners/registries dựa trên marker interface.

Nếu class definition thực sự đã weave, reflection trên class ấy có thể thấy type/method additions. Nếu introduction chỉ thuộc proxy, reflection trên proxy có thể thấy interface mà reflection trên target không thấy.

### 11.1. GetMethods khác GetDeclaredMethods

getMethods xét các public methods có thể truy cập từ type, bao gồm inherited methods theo Java reflection contract; getDeclaredMethods tập trung methods declared tại class. Chúng không đồng nhất.

Một introduced method có thể được biểu diễn ở các lớp khác nhau tùy mechanism. Hãy kiểm tra type thật đang được quan sát.

### 11.2. Annotation trên implementation không tự có ở interface/proxy

Annotation placement và inheritance rules khác nhau theo annotation target, method, class, interface. Đừng cho rằng annotation của một method implementation xuất hiện khi chỉ reflect interface Method.

### 11.3. Những tác động gián tiếp

Một serializer, validator, object mapper hoặc policy registry có thể chọn nhánh theo interface. Thêm interface cho một class có thể làm chính các components ấy đổi behavior dù source của chúng không thay đổi.

## 12. Class loader, weaving phase và loaded classes

Java class identity không chỉ là binary name; **defining ClassLoader** là thành phần của runtime type identity.

Hai interfaces cùng tên do hai defining loaders khác nhau load có thể không compatible. Dẫn tới:

- ClassCastException.
- LinkageError hoặc visibility issue.
- isAssignableFrom false dù class names trông giống.
- Plugin/service module không thấy introduced API.
- Runtime deploy type khác với build/test.

### 12.1. Weaving tại thời điểm thích hợp

Nếu type relations phải thay trên binary, weaving thường cần diễn ra ở một phase mà runtime type còn có thể được định nghĩa với structure mới. Không mặc định JVM đã load class rồi cho phép thay superclass/interface bằng arbitrary redefinition.

### 12.2. Phạm vi weaving

Nếu build chỉ weave package A còn production load một class cùng tên từ module/loader khác, behavior có thể khác. Cần bảo đảm mapping target types, weaving configuration và generated artifacts nhất quán.

### 12.3. Consumer compile against type introduction

Consumer source dùng Invoice như một Auditable có thể phải compile trong một môi trường hiểu type introduction. Nếu chạy với raw Invoice không woven, những casts, method references hoặc links có thể fail tùy tình huống.

Kết luận: **compile-time type view và runtime bytecode phải thống nhất**.

## 13. Source, binary và behavioral compatibility

Ba góc nhìn:

| Loại | Câu hỏi |
|---|---|
| **Source compatibility** | Source cũ recompile với type mới được không? |
| **Binary compatibility** | Bytecode đã compile có link và chạy được không? |
| **Behavioral compatibility** | Kết quả, dispatch, side effects, type-based policies có còn đúng? |

Ví dụ một class thêm interface có thể vẫn giữ các method cũ nên binary consumer cũ dùng method đó vẫn chạy, nhưng source recompile có thể gặp **overload ambiguity**. Một library dùng instanceof để phân nhánh có thể đổi behavior ngay cả khi không có lỗi compilation.

### 13.1. API contract là public dependency

Nếu Auditable interface là một public API và được introduction vào nhiều classes, version mới của Auditable thêm abstract method có thể yêu cầu cập nhật những implementations đó. Không thể để structural introduction là hidden build detail không được versioning.

### 13.2. Compile/test/production parity

Cần chạy tests trên **artifact sau weave** và deployed runtime, không chỉ source class ban đầu. Nếu runtime một số nodes dùng type introduction còn nodes khác không, behavior của casts/discovery có thể không nhất quán.

### 13.3. Compatibility phụ thuộc consumers

Một consumer chỉ dùng Worker.work có thể không bị ảnh hưởng bởi Tagged introduction. Consumer dùng Tagged casts hoặc serializers dựa interface có thể bị ảnh hưởng mạnh. Không có câu trả lời tương thích tuyệt đối nếu chưa biết use sites.

## 14. Serialization và persistence

Một introduced field hay interface có thể ảnh hưởng serialization form hoặc nhánh serializer chọn.

Những câu hỏi:

- Introduced field có nằm trong serialized state không?
- SerialVersionUID hoặc binary compatibility có thay đổi không?
- Adapter/proxy handler/delegate có serializable contract không?
- Deserialization trên runtime không weave có thiếu capability không?
- Một marker interface mới có đổi serialization strategy không?
- Data versions cũ được đọc bởi class mới thế nào?
- External persistence mapper dùng reflection có nhìn thấy members mới không?

**Serializable marker không tự bảo đảm object graph và trạng thái handler/delegate có thể serialize đúng.** Nếu fields introduction chứa mutable/global state, lifecycle còn phức tạp hơn.

## 15. Reference identity, equality và cache

Một adapter P bọc target T thường có **P != T** theo reference identity. Dù cả hai cùng đại diện một service logical, hai objects có monitor, lifecycle và hash/identity semantics khác.

Nếu cache dùng P làm key, raw T có thể không tìm thấy entry. Một IdentityHashMap chắc chắn phân biệt hai references khi chúng là hai objects.

Không forward equals từ adapter xuống target một chiều:

~~~text
P.equals(T) = T.equals(T) = true
T.equals(P) = false
~~~

Điều này có thể vi phạm symmetry khi T giữ identity equality mặc định.

Muốn cache theo thực thể nghiệp vụ, dùng một **business ID bất biến** với contract rõ, thay vì ép proxy và target có cùng object identity.

## 16. Introduced mutable state và concurrency

Giả sử introduction thêm mutable counter vào mỗi Invoice:

~~~text
Invoice:
   introduced int auditCount
   introduced incrementAuditCount()
~~~

Nếu cùng Invoice instance được nhiều threads thao tác, increment bằng ++ vẫn có thể **lost update**. Structural introduction không tự thêm synchronization.

Nếu trạng thái được lưu trong một shared aspect field hay external map thay vì per-object field, nhiều Invoices có thể cùng chia sẻ state và yêu cầu concurrency control khác.

Cân nhắc:

- Immutable introduced metadata.
- AtomicInteger/AtomicLong nếu cần atomic counter.
- Lock bảo vệ multi-field invariant.
- ConcurrentMap với key/lifecycle policy đúng.
- ThreadLocal cho state theo thread, có cleanup.
- Data isolation theo instance khi semantics thực sự per-object.

### 16.1. Initialization và lifecycle

Introduced fields cần initialization đáng tin cậy trước khi methods mới được gọi. Constructors, serialization, cloning và reflection creation có thể đi qua các đường khác nhau. Cần test state đã sẵn sàng ở mọi object creation path.

### 16.2. External state map retention

Nếu aspect giữ Map<Target, State> với strong references, Map có thể giữ target sống lâu. Weak key/caching strategy cũng cần test equality, GC và concurrency. Không dùng identityHashCode như unique ID tuyệt đối.

## 17. Structural introduction có thể đổi pointcut matches

Một aspect A bổ sung Auditable vào Invoice; aspect B có type-based pointcut chọn methods trên những đối tượng Auditable.

Nếu B áp dụng dựa trên woven hierarchy, introduction của A có thể làm **tập join points của B thay đổi**. Đây là semantic dependency dù hai aspects không gọi nhau.

Nhưng exact matching còn phụ thuộc:

- Call hay execution join point.
- Static declaring type hay runtime target type.
- Type pattern semantics của AOP language.
- Weaver precedence và instrumentation phase.
- Proxy interface introduction hay binary structural changes.
- Class loader và package scope.

Không suy rằng mọi pointcut sẽ luôn match theo cùng quy tắc khi type hierarchy đổi. Cần positive và negative matching tests.

### 17.1. Multiple introductions

Hai aspects có thể cố thêm cùng method với implementations khác nhau, hoặc giới thiệu interfaces có default conflicts. Cần chính sách conflict/precedence rõ; không tin một aspect tự động “thắng” aspect khác.

### 17.2. Advice khác vẫn có thể bypass

Nếu capability chỉ nằm ở proxy P, những lời gọi trực tiếp trên T không tự đi qua P. Nếu behavior introduced phụ thuộc một advice ở P, cần kiểm soát reference distribution và self-invocation theo mechanism thực.

## 18. Khi nào nên dùng structural introduction?

Có thể hợp lý nếu:

1. Nhiều target types thực sự cần public capability/interface chung.
2. Contract đó có ý nghĩa rõ ràng và có implementation đủ đúng.
3. Build/weaving pipeline được quản lý chặt.
4. Patterns giới hạn tập target và test đúng đối tượng bị/không bị áp dụng.
5. Các consumers thực sự cần type-level contract.
6. Source/binary/behavioral compatibility được đánh giá.
7. Class loaders và deployment có cùng woven type information.
8. Cách tổ chức bằng aspect tăng tính rõ ràng hơn chi phí ẩn của API change.

Không cần structural type change nếu mục đích chỉ là:

- Ghi log invocation.
- Đo thời gian method.
- Đếm operation.
- Kiểm tra quyền ở một method boundary.
- Cache kết quả mà không cần exposing một interface mới.

Các mục tiêu ấy thường có thể dùng advice, decorator hoặc composition rõ ràng.

## 19. Phương án đơn giản hơn: explicit interface

Nếu source class nằm trong quyền kiểm soát và capability thật sự là một domain contract:

~~~java
final class Invoice implements Auditable {
    @Override
    public String auditId() {
        return "...";
    }
}
~~~

Đây là snippet minh họa, chưa độc lập. Lợi ích:

- Type relation hiện rõ trong source.
- IDE, Java compiler và reviewers dễ nhận biết.
- Không có hidden weaving requirement để type-check.
- Tests không cần đoán object đã introduction hay chưa.

Nhược điểm: phải sửa nhiều classes, có thể tạo repetition hoặc trộn concern vào domain nếu introduction phục vụ crosscutting role thuần.

## 20. Phương án khác: adapter, decorator và composition

Adapter có thể expose một interface mới chỉ tại boundary cần dùng:

~~~text
Raw Invoice T
      |
      v
AuditableInvoiceAdapter P
      |
      v
Consumer sees Auditable
~~~

Ưu điểm:

- Không cần chỉnh sửa class binary gốc.
- Áp dụng được cho third-party types.
- Ranh giới capability rõ khi API trả adapter.
- Dễ unit test riêng.

Nhược điểm:

- Hai object identities.
- Caller có T thô không tự thấy Auditable.
- Cast/reflection behavior trên T khác P.
- Equality/hashCode/serialization cần contract riêng.
- Delegate có thể bỏ sót methods hoặc làm sai concurrency boundaries.

Nếu mục tiêu chỉ là gắn metadata cho một class mà không cần caller cast, một metadata registry cũng có thể đủ, nhưng cần kiểm soát class loader/lifecycle.

## 21. Thứ tự đánh giá và quy trình migration

Một kế hoạch migration nên gồm:

1. **Liệt kê use sites:** casts, instanceof, reflection, overloads, registry lookups.
2. **Vẽ type graph trước/sau:** interfaces, superclass, inherited/default methods.
3. **Xác định mechanism:** woven binary hay proxy/adapter.
4. **Kiểm tra method contracts:** return/exception/thread safety/semantics.
5. **Kiểm tra collisions:** signature, generics erasure, default methods.
6. **Kiểm tra final/sealed constraints** và class loading.
7. **Tạo compiler tests:** source trước/sau và overload ambiguities.
8. **Tạo runtime tests:** cast, instanceof và isAssignableFrom trên object thật.
9. **Tạo reflection/serializer tests:** trên binary deployed, không chỉ type mocks.
10. **Kiểm tra điểm cấp object:** factory có trả P hay T?
11. **Kiểm tra identity:** equality, cache keys, lock monitors.
12. **Kiểm tra concurrency:** introduced fields/state thread-safe nếu cần.
13. **Kiểm tra pointcut interactions:** advice khác match rộng hơn không?
14. **Kiểm tra old/new artifacts:** link và deploy consistency.
15. **Tài liệu hóa API/versioning:** giới hạn type capability và fallback khi không weave.

## 22. Ma trận kiểm thử

| Kịch bản | Cần xác minh |
|---|---|
| Target raw không implement capability | instanceof false, cast thất bại khi dùng sai |
| Adapter implements capability | instanceof/cast thành công trên adapter |
| Structural-woven target | Runtime Class có interface/member mới |
| Proxy và target cùng workflow | Reference identity khác, dù kết quả delegate giống |
| Static type Worker | Chỉ Worker methods có thể gọi trực tiếp |
| Overloads Worker/Tagged | Compiler chọn theo static type |
| Concrete class implements hai interfaces | Ambiguous overload được xử lý |
| Generic List<Worker> | Không tự coi là List<Tagged> |
| Reflection class relation | getInterfaces/isAssignableFrom đúng deployed type |
| Introduced method | Return/exception semantics đúng contract |
| Default method conflicts | Compiler/weaver báo hoặc override hợp lệ |
| Final/sealed types | Không tạo hierarchy bất hợp lệ |
| Class loader isolation | Type identity và cast không nhầm |
| Serialization | Old/new data được xử lý đúng |
| Factory/distribution | Caller nhận đúng object có capability |
| HashMap/IdentityHashMap | Equality/caching không nhầm P với T |
| Concurrent mutable field | Không lost update |
| Woven type consumer vs raw runtime | Mismatch bị phát hiện |
| Other aspects by interface pattern | Pointcut matches có kiểm soát |
| Negative target types | Không bị giới thiệu interface nhầm |
| API version bump | Giữ source/binary/behavioral contract theo yêu cầu |

## 23. Những sai lầm phổ biến

**1.** Cho rằng before/around advice tự thay Java inheritance.

**2.** Cho rằng proxy implement Tagged thì raw target cũng implement Tagged.

**3.** Đồng nhất overload resolution với runtime method dispatch.

**4.** Bỏ qua compiler static type khi gọi introduced methods.

**5.** Cast raw target không có introduced interface rồi ngạc nhiên vì ClassCastException.

**6.** Cho rằng marker interface không có tác động hành vi.

**7.** Thêm interface nhưng không cung cấp method implementation đúng contract.

**8.** Không kiểm tra default method conflict.

**9.** Nghĩ generics invariant tự biến thành covariance sau introduction.

**10.** Cho rằng final class có thể được subclass như class thường.

**11.** Nghĩ loaded class có thể thay superclass/interface tùy ý trong JVM.

**12.** Bật weaving khi test nhưng không bật khi deploy.

**13.** Không nhận ra recompile có overload ambiguity dù binary cũ vẫn chạy.

**14.** Dùng adapter equals bất đối xứng với target.

**15.** Quên giới hạn ClassLoader type identity.

**16.** Cho rằng source annotation ở target luôn hiện trên proxy methods.

**17.** Dùng introduced mutable field không đồng bộ ở shared object.

**18.** Không kiểm thử pointcut của aspect khác sau thay đổi hierarchy.

**19.** Dùng interface quá rộng rồi cho nhiều methods throw UnsupportedOperationException.

**20.** Chọn structural weaving khi một explicit interface/adapter nhỏ đã đáp ứng yêu cầu.

## 24. Câu hỏi ôn tập và đáp án

**Câu 1.** Trước method của Invoice có logging advice. Invoice đã implement Auditable chưa?

**Đáp:** Chưa; advice hành vi không tự làm type introduction.

**Câu 2.** TaggedAdapter implement Tagged và delegate CoreWorker. Raw CoreWorker có thể cast Tagged không?

**Đáp:** Không, trừ khi class CoreWorker thực sự có quan hệ type đó qua cơ chế khác.

**Câu 3.** Vì sao route(adapted) chọn Worker trong demo?

**Đáp:** Static type của biến adapted là Worker, overload được giải quyết lúc compile.

**Câu 4.** Vì sao route(taggable) chọn Tagged?

**Đáp:** Biến taggable có static type Tagged.

**Câu 5.** Woven CoreWorker implements Tagged thật có thể thay đổi reflection không?

**Đáp:** Có nếu deployed runtime Class chứa interface mới.

**Câu 6.** List<Invoice> tự là List<Auditable> khi Invoice extends/implements Auditable không?

**Đáp:** Không, generics invariant.

**Câu 7.** Tại sao interface marker vẫn có thể đổi behavior của một serializer?

**Đáp:** Serializer có thể chọn strategy dựa vào instanceof hoặc interface metadata.

**Câu 8.** Khi hai unrelated interfaces có cùng default method, introduction có thể gặp lỗi gì?

**Đáp:** Method conflict, cần implementation giải quyết hợp lệ.

**Câu 9.** Một class final có thể được subclass proxy không?

**Đáp:** Không theo Java subclassing rules.

**Câu 10.** Structural weaving có luôn giống subclass proxy không?

**Đáp:** Không; direct binary weaving và subclassing là hai mechanisms khác nhau.

**Câu 11.** Source recompile có thể fail dù bytecode cũ vẫn link không?

**Đáp:** Có, ví dụ overload trở thành ambiguous.

**Câu 12.** Vì sao Class.isAssignableFrom có thể false dù hai interface names giống nhau?

**Đáp:** Chúng có thể do những ClassLoaders khác nhau định nghĩa.

**Câu 13.** Introduced mutable field count++ có thread-safe mặc định không?

**Đáp:** Không, concurrency vẫn cần synchronization/atomic state.

**Câu 14.** Một aspect khác chọn Auditable join points có bị introduction ảnh hưởng không?

**Đáp:** Có thể, vì type hierarchy mới thay tập matching.

**Câu 15.** Có nên dùng structural introduction chỉ để log một operation không?

**Đáp:** Thường không cần; một method-level advice hoặc decorator có thể đủ.

**Câu 16.** Khi runtime cấp raw T nhưng documentation hứa capability trên P, lỗi nằm ở đâu?

**Đáp:** Hợp đồng factory/distribution không nhất quán về object được cung cấp cho caller.

## 25. Sơ đồ tóm tắt

~~~text
             CẦN THÊM CAPABILITY?
                       |
                       v
            Cần Java subtype thật?
              /              \
            KHÔNG             CÓ
              |                |
              v                v
          Advice hoặc    Có thể sửa source?
          metadata          /       \
                         CÓ         KHÔNG
                          |            |
                          v            v
                   implements       Structural
                   trực tiếp        introduction?
                          |            |
                          +------+-----+
                                 |
                                 v
                 Xác định runtime mechanism
                woven class / adapter / proxy
                                 |
                 +---------------+----------------+
                 |               |                |
                 v               v                v
             instanceof        overload         reflection
             cast/identity     static types     class metadata
                 |               |                |
                 +---------------+----------------+
                                 |
                                 v
                      Contract + QA migration
                  compile/runtime consistency,
                  generics, compatibility, state,
                  class loaders, pointcut effects
~~~

**Kết luận:** Type relationship introduction là một dạng **structural crosscutting** có hệ quả trực tiếp với mã sử dụng. Cần phân biệt **type của class được weave** với **type mở rộng chỉ thuộc một proxy/adapter**; kiểm chứng instanceof/cast, static overload selection, generics, reflection và object identity trên đúng object. Mọi introduction còn phải giữ Java type rules, hợp đồng interface, tương thích nguồn/binary/behavioral, versioning, concurrency và tác động tới các pointcut khác. Chỉ dùng thay đổi type khi có một capability-level contract thực sự; nếu chỉ cần bổ sung behavior, một advice hoặc explicit adapter thường dễ lý giải hơn.

## Tài liệu tham khảo

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): structural crosscutting và inter-type declarations trong một ngôn ngữ AOP.
- [JLS 17 — Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html): Java type system.
- [JLS 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): class hierarchy và method rules.
- [JLS 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): interfaces/default methods.
- [JLS 17 — Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): cast, instanceof, overload resolution.
- [JLS 17 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): binary compatibility.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): reflection, assignability.
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): interface-based proxy capabilities.
