# Generic bị xóa và metadata phụ thuộc nội dung class file trong Java Reflection

## 1. Hai sự thật phải hiểu cùng lúc

Trong Java, **generic dùng cơ chế type erasure (xóa kiểu)**: phần lớn đối số kiểu như `String` trong `List<String>` không trở thành một kiểu runtime riêng của object. Hai đối tượng `new ArrayList<String>()` và `new ArrayList<Integer>()` đều có lớp runtime là `java.util.ArrayList`; gọi `getClass()` không cho biết chúng đã được khai báo với đối số kiểu nào.

Tuy nhiên, **reflection vẫn có thể đọc nhiều thông tin generic của *khai báo***. Ví dụ, khi một lớp khai báo field `List<String> names`, `Field.getGenericType()` có thể báo `java.util.List<java.lang.String>`, dù `Field.getType()` chỉ trả `java.util.List`. Điều này không mâu thuẫn với erasure: thông tin về **khai báo** có thể được trình biên dịch lưu trong metadata của class file, còn đối số kiểu được dùng tại một vị trí tạo instance thông thường thường không lưu theo từng instance.

Điều quyết định chất lượng kết quả phản chiếu là: **chương trình đang hỏi về đối tượng runtime hay về khai báo được lưu trong class file? Metadata cần thiết có thực sự tồn tại và hợp lệ không?**

Ba lớp thông tin cần phân biệt:

1. **Kiểu khai báo tại thời gian biên dịch:** `List<String> names`; compiler dùng đối số `String` để kiểm tra thao tác tại nơi có đủ thông tin kiểu.
2. **Kiểu thực sự của object tại runtime:** ví dụ `ArrayList.class`, không phải một lớp riêng `ArrayList<String>.class`.
3. **Thông tin generic khai báo còn được giữ trong class file:** type parameter `T`, signature của `List<String>`, generic superclass `Base<Integer>`, method `<U> U copy(U value)`; reflection có thể đọc nếu metadata tương ứng được lưu và được diễn giải thành công.

## 2. Type erasure thực sự làm gì?

Trong các trường hợp phổ biến, trình biên dịch xóa đối số generic khỏi type sử dụng trong bytecode runtime và thay type variable bằng **erasure** của nó:

- `T` không có bound → thường erasure là `Object`.
- `T extends Number` → erasure là `Number` (bound đầu tiên xác định erasure trong trường hợp nhiều bound).
- `List<String>` và `List<Integer>` → cùng kiểu raw runtime `List`.
- Compiler có thể chèn phép cast tại vị trí lấy giá trị generic, và có thể tạo **bridge method** để duy trì tính đa hình sau erasure.

Ví dụ ý tưởng:

```java
// Hai đoạn minh họa riêng: không phải chương trình độc lập.
class Box<T extends Number> {
    T value;
}
class TextBox<T> {
    T value;
}
```

Erasure của field `Box.value` là `Number`; của `TextBox.value` là `Object`. Dù vậy, nếu Signature metadata tồn tại, `getGenericType()` của hai field vẫn có thể cho biết type variable `T` trong khai báo.

**Hệ quả thực tế:**

- Không thể viết `List<String>.class` hoặc `List<Integer>.class`; chỉ có `List.class`.
- Không thể dùng `obj instanceof List<String>` do đối số kiểu không reifiable (trừ những trường hợp wildcard dạng reifiable như `List<?>`).
- Việc overload hai phương thức chỉ khác đối số generic, ví dụ `handle(List<String>)` và `handle(List<Integer>)`, gây xung đột chữ ký sau erasure.
- Không thể viết `new T()` chỉ dựa trên type parameter; cần constructor/factory hoặc `Class<T>` truyền vào với giới hạn thích hợp.
- Không thể mặc định tạo mảng `new List<String>[5]`; cách biểu diễn mảng và generics có quy tắc reifiability khác nhau.
- Reflection có thể giúp đọc metadata khai báo, **không tự làm việc kiểm tra phần tử của một `ArrayList` trở thành an toàn ở runtime**. Tham chiếu raw type/unchecked cast vẫn có thể phá vỡ giả định kiểu và dẫn đến `ClassCastException` ở nơi sử dụng.

Erasure không có nghĩa “Java xóa hết mọi ký tự generic khỏi file .class”. Bytecode descriptor và generic Signature phục vụ mục đích khác nhau.

## 3. Metadata trong class file: descriptor và Signature

Một class file có cấu trúc mô tả lớp, field và method để JVM liên kết, kiểm tra và thực thi. Chẳng hạn một field khai báo `List<String> names` thường có:

- **Field descriptor** biểu diễn kiểu erased như `Ljava/util/List;`; JVM dùng biểu diễn cơ bản này khi giải quyết field.
- **Generic `Signature` attribute** biểu diễn thêm đối số kiểu `String` (được sinh bởi trình biên dịch khi cần). Đây là metadata riêng mà API generic reflection có thể phân tích.

Với field `T value` trong `class Box<T extends Number>`, descriptor thể hiện `Number`, còn Signature có thể lưu dạng tham chiếu đến type variable `T`. Với `class IntegerBox extends Box<Integer>`, Signature của `IntegerBox` có thể lưu việc superclass được tham số hóa bằng `Integer`.

**`Signature` là một thuộc tính class file và không được bảo đảm luôn hiện diện.** Công cụ tạo hoặc biến đổi bytecode, obfuscator/shrinker hay việc cung cấp class file thiếu/sai metadata có thể khiến reflection chỉ thấy kiểu đã erasure hoặc không phân tích được generic signature. Vì thế:

- `Field.getType()`, `Method.getReturnType()` và `Method.getParameterTypes()` trả kiểu `Class<?>` ở mức erased/runtime.
- `Field.getGenericType()`, `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`, `Class.getGenericSuperclass()` và `Class.getGenericInterfaces()` cố đọc thông tin generic trên **khai báo**, nếu class file có metadata phù hợp.
- `Class.getTypeParameters()`, `Method.getTypeParameters()` hoặc `Constructor.getTypeParameters()` mô tả **type variables do thành phần ấy khai báo**, không phải đối số kiểu thật của mọi instance.
- Một phương thức generic chỉ có descriptor runtime chưa đủ để tái dựng toàn bộ tên/bound/đối số generic trong nguồn; metadata nếu thiếu không thể được suy luận chính xác chỉ từ erased descriptor.

Khi Signature không được ghi cho một khai báo, API `getGeneric...` thường chỉ còn thông tin tương ứng với kiểu raw/erased; không có phép biến đổi thông minh nào khôi phục kiểu nguồn tùy ý một cách chắc chắn.

## 4. Ví dụ Java 17+ chạy được: xem erasure và generic metadata cạnh nhau

Tạo tệp `ErasureMetadataDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.ArrayList;
import java.util.List;

public class ErasureMetadataDemo {
    static class Repository<T extends Number> {
        T count;
        List<String> labels;
        List<? extends Number> numbers;

        public <U> List<U> same(List<U> values) {
            return values;
        }
    }

    static class IntegerRepository extends Repository<Integer> {
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        List<String> words = new ArrayList<>();
        List<Integer> ids = new ArrayList<>();
        System.out.println("Same runtime class: "
                + (words.getClass() == ids.getClass()));

        Field count = Repository.class.getDeclaredField("count");
        System.out.println("Field erased: "
                + count.getType().getTypeName());
        System.out.println("Field generic: "
                + count.getGenericType().getTypeName());

        Field labels = Repository.class.getDeclaredField("labels");
        System.out.println("List erased: "
                + labels.getType().getTypeName());
        System.out.println("List generic: "
                + labels.getGenericType().getTypeName());

        ParameterizedType parameterized =
                (ParameterizedType) labels.getGenericType();
        System.out.println("Type argument: "
                + parameterized.getActualTypeArguments()[0].getTypeName());

        Field numbers = Repository.class.getDeclaredField("numbers");
        ParameterizedType wildcardList =
                (ParameterizedType) numbers.getGenericType();
        System.out.println("Wildcard: "
                + wildcardList.getActualTypeArguments()[0].getTypeName());

        Type superclass = IntegerRepository.class.getGenericSuperclass();
        System.out.println("Generic superclass: "
                + superclass.getTypeName());

        Method method = Repository.class.getDeclaredMethod("same", List.class);
        System.out.println("Method erased return: "
                + method.getReturnType().getTypeName());
        System.out.println("Method generic return: "
                + method.getGenericReturnType().getTypeName());

        TypeVariable<?> variable = Repository.class.getTypeParameters()[0];
        System.out.println("Type variable: " + variable.getName());
        System.out.println("Type variable bound: "
                + variable.getBounds()[0].getTypeName());
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ErasureMetadataDemo.java
java ErasureMetadataDemo
```

Output dự kiến:

```text
Same runtime class: true
Field erased: java.lang.Number
Field generic: T
List erased: java.util.List
List generic: java.util.List<java.lang.String>
Type argument: java.lang.String
Wildcard: ? extends java.lang.Number
Generic superclass: ErasureMetadataDemo$Repository<java.lang.Integer>
Method erased return: java.util.List
Method generic return: java.util.List<U>
Type variable: T
Type variable bound: java.lang.Number
```

**Đọc kết quả theo từng lớp:**

1. `words` và `ids` là hai instance khác nhau, nhưng `getClass()` chỉ thấy cùng implementation runtime `ArrayList`; không có tham số kiểu `String`/`Integer` gắn vào từng object.
2. `count.getType()` là `Number.class` vì `T extends Number` có erasure là `Number`. `count.getGenericType()` trả một `TypeVariable` mô tả `T` đã khai báo.
3. `labels.getType()` trả `List.class`, còn `labels.getGenericType()` trả một `ParameterizedType` có đối số `String`. Dữ liệu này đến từ **chữ ký khai báo field trong class file**.
4. `numbers` chứa một đối số kiểu wildcard; generic reflection có thể trả `WildcardType`, nơi upper bound là `Number`. Không được suy ra danh sách này đang chứa giá trị cụ thể nào.
5. `IntegerRepository.class.getGenericSuperclass()` đọc chữ ký của mệnh đề `extends Repository<Integer>`. Đây là metadata thuộc **khai báo subclass**, không phải mọi instance `Repository` tự biết `Integer`.
6. Method `same(List<U>)` có kiểu trả về erased là `List`, trong khi metadata khai báo cho biết `List<U>`. Vì parameter runtime là raw `List`, việc tìm method phải dùng `getDeclaredMethod("same", List.class)`.
7. `getTypeParameters()` mô tả `T` do `Repository` khai báo; `getBounds()` cho biết bound `Number`. Nó không tự suy ra `T = Integer` từ một instance `new Repository<Integer>()`.

## 5. Các kiểu `java.lang.reflect.Type` và cách đọc đúng

API generic reflection dùng `Type` làm kiểu gốc cho những dạng thông tin phong phú hơn `Class<?>`:

| Dạng `Type` | Mô tả | Ví dụ đọc từ khai báo |
| --- | --- | --- |
| `Class<?>` | Kiểu runtime cụ thể hoặc kiểu raw | `String`, `List`, `int[]` |
| `ParameterizedType` | Kiểu khai báo có đối số kiểu | `List<String>`, `Map<String, Integer>` |
| `TypeVariable<?>` | Tham số kiểu được khai báo bởi class/method/constructor | `T` trong `class Box<T>` |
| `WildcardType` | Wildcard với upper/lower bounds | `? extends Number`, `? super Integer` |
| `GenericArrayType` | Kiểu mảng có component generic không reifiable | `T[]`, `List<String>[]` trong khai báo |

Với `ParameterizedType` có thể xem `getRawType()`, `getActualTypeArguments()` và `getOwnerType()`. Với `TypeVariable` có `getBounds()` và `getGenericDeclaration()`; với `WildcardType` có `getUpperBounds()` và `getLowerBounds()`. Các giá trị trả về có thể là đối tượng `Type` lồng nhau nên phải đi theo cây thông tin, không mặc định ép về `Class<?>`.

**Phân biệt `Type.getTypeName()` và runtime class:** chuỗi `java.util.List<java.lang.String>` là cách biểu diễn metadata kiểu tổng quát, không chứng minh có một `Class` mới mang đúng tên ấy; không nên nối chuỗi đó rồi truyền cho `Class.forName`. Reflection `Type` phục vụ đọc/mô tả cấu trúc kiểu, còn các thao tác như `Class.isInstance` hoạt động ở quan hệ kiểu runtime có thể kiểm tra.

Các API `AnnotatedType`, `getAnnotatedType()` và `getAnnotatedReturnType()` dùng khi cần **annotation gắn vào vị trí sử dụng kiểu** (type-use annotation). Chúng là vấn đề metadata bổ sung, không thay đổi nguyên lý erasure; cần policy retention thích hợp để annotation có thể phản chiếu lúc chạy.

## 6. Vì sao không thể lấy `List<String>` từ mọi object?

Xét đoạn code:

```java
// Minh họa đặt trong một method, không phải chương trình độc lập:
List<String> first = new ArrayList<>();
List<Integer> second = new ArrayList<>();
Class<?> firstClass = first.getClass();
Class<?> secondClass = second.getClass();
System.out.println(firstClass == secondClass); // true
```

Thông tin `String` hoặc `Integer` ở biến nguồn là kiến thức compile-time của trình biên dịch; gọi `first.getClass()` chỉ trả `java.util.ArrayList`. Nếu object được đưa qua API `Object` hay raw `List`, API `getClass()` không thể suy ra đối số generic ban đầu chỉ từ dữ liệu runtime. Việc đọc các phần tử hiện có cũng không chứng minh phần tử tương lai có kiểu nào, và danh sách trống không cung cấp bằng chứng kiểu.

**Một ngoại lệ quan trọng là metadata đã được ghi trong khai báo class cụ thể.** Ví dụ một subclass:

```java
// Khai báo ví dụ, không phải chương trình độc lập:
class StringList extends ArrayList<String> {}
```

`StringList.class.getGenericSuperclass()` có thể mô tả `ArrayList<String>` vì đối số `String` được ghi trong **superclass signature của StringList.class**. Cách thường được gọi là *super type token* (chẳng hạn anonymous subclass) tận dụng quy tắc này. Đây **không phải** reification của `ArrayList<String>` cho mọi object; nó lưu/đọc một khai báo lớp mới, và vẫn tùy thuộc metadata class file. Khi anonymous subclass vẫn còn type variable, việc đọc signature có thể chỉ thấy biến kiểu đó, không tự tìm được đối số cuối cùng của một lời gọi generic bất kỳ.

Nếu API thực sự cần kiểu phần tử lúc chạy, giải pháp thường rõ ràng hơn là **truyền token kiểu tường minh** (ví dụ `Class<T>` cho kiểu có thể biểu diễn bằng `Class`, hoặc một cấu trúc `Type`/`TypeToken` đủ phong phú cho dạng generic), hoặc lưu metadata trong schema/descriptor của ứng dụng. Token kiểu không biến JVM thành bộ kiểm tra nội dung mọi collection.

## 7. Metadata phụ thuộc công cụ biên dịch và xử lý bytecode

Tài liệu hoặc framework không nên mặc định rằng class file luôn có đầy đủ thông tin như trong mã nguồn.

- **Generic `Signature`:** các khai báo có generic signature thường được `javac` ghi vào class file; công cụ bytecode transformation, shrinker hoặc obfuscator có thể bỏ hoặc thay đổi thuộc tính này. Khi không có nó, không thể chắc chắn tái tạo được tất cả type argument từ descriptor đã erasure.
- **Debug information:** các thuộc tính như `LineNumberTable`, `LocalVariableTable` và `LocalVariableTypeTable` phục vụ các nhu cầu khác. `javac -g:none` ảnh hưởng thông tin debug; không nên coi nó là lệnh “xóa toàn bộ generic Signature”. Generic metadata được API `Field`/`Method` đọc không đồng nghĩa thông tin biến cục bộ còn đầy đủ.
- **Tên parameter:** `javac -parameters` ghi metadata tên parameter của method/constructor cho `Parameter.getName()` (khi dữ liệu này có mặt). Điều này khác với `getGenericParameterTypes()`, vốn phục vụ kiểu generic của parameter.
- **Annotation:** chỉ những annotation phù hợp điều kiện lưu giữ runtime mới được các API annotation reflection nhìn thấy. `RetentionPolicy.CLASS` vẫn có thể được ghi trong class file nhưng không phải annotation runtime thông thường; `RetentionPolicy.SOURCE` không tồn tại trong class file sau biên dịch. Generic Signature và annotation là hai kênh metadata khác nhau.
- **Bridge và synthetic method:** compiler có thể tạo bridge method do erasure để bảo toàn dispatch đa hình. Khi quét `getDeclaredMethods()`, công cụ có thể nhìn thấy method do compiler sinh; kiểm tra `Method.isBridge()` và `Method.isSynthetic()` khi lựa chọn phương thức nghiệp vụ, tránh đếm trùng hoặc xử lý nhầm method cầu nối.
- **Binary compatibility:** việc sửa/loại metadata generic có thể không thay đổi ngay descriptor JVM của method, nhưng có thể làm hỏng khả năng phân tích của framework, serializer, mapper hoặc generator cần dữ liệu type đầy đủ.

Nếu Signature bị hỏng hoặc trỏ đến type không hiện diện, các API generic reflection có thể thất bại bằng `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` (tùy tình huống). Điều này khác với class đã được load nhưng lỗi quyền gọi method; không dùng `setAccessible(true)` như cách khôi phục Signature bị mất.

## 8. Xem class file để đối chiếu API reflection

Dùng chính file của ví dụ `ErasureMetadataDemo.java` đã biên dịch ở phần 4:

```bash
javap -v 'ErasureMetadataDemo$Repository'
```

Trên PowerShell, có thể dùng cùng cú pháp dấu nháy đơn; trên các shell phổ biến dấu nháy đơn cũng ngăn ký tự `$` bị diễn giải là biến. Kết quả dài và phụ thuộc phiên bản compiler, vì vậy **không nên chép nguyên output** để so khớp từng dòng; hãy tìm các mục:

- `descriptor: Ljava/lang/Number;` cho field `count` cùng `Signature` liên quan type variable `T`.
- `descriptor: Ljava/util/List;` cho field `labels` cùng `Signature` mô tả `List<String>`.
- `Signature` ở khai báo class hoặc method để lưu type parameter, bound và generic return/argument.

`javap -v` là cách quan sát bytecode/classfile trực tiếp; `javap -p` chỉ làm rõ thành viên private, không tự hiển thị mọi generic Signature dạng raw. Nếu bytecode đã bị công cụ xử lý sau build, hãy chạy `javap` trên **class file thực sự được đóng gói/triển khai**, không chỉ bản build tại máy phát triển.

Không lấy sự xuất hiện của generic signature trong ví dụ chuẩn do `javac` biên dịch để kết luận mọi compiler, enhancer, proxy hoặc classfile đều giữ metadata tương tự.

## 9. Quy trình quyết định khi thiết kế công cụ reflection

1. **Bạn muốn kiểm tra object hay khai báo?** Nếu cần kiểm tra object có thuộc kiểu runtime nào, dùng `getClass()`, `instanceof` hoặc `Class.isInstance`. Nếu cần type argument trong field/method/superclass, dùng các API generic reflection trên nơi khai báo.
2. **Giá trị kiểu cần nằm trong instance?** Đừng suy ra từ `List.class`; truyền `Class<T>`, `Type` token hoặc schema tường minh. Với các generic lồng nhau, `Class<T>` một mình không đủ để mô tả `List<String>`.
3. **Thông tin có sẵn trong class file thật không?** Kiểm tra `Signature` bằng `javap -v` hoặc công cụ classfile. Chú ý compiler, obfuscation, bytecode weaving và packaging.
4. **`Type` có dạng nào?** Duyệt `ParameterizedType`, `TypeVariable`, `WildcardType` hoặc `GenericArrayType` theo ngữ nghĩa thay vì cast mù quáng về `Class<?>`.
5. **Có thể thất bại khi đọc metadata không?** Xử lý lỗi class/linkage và signature malformed/missing theo cách framework định nghĩa; không coi metadata thiếu là tín hiệu type argument bằng `Object` trong mọi trường hợp.
6. **Có nguy cơ nhầm generic metadata với runtime enforcement?** Kiểm tra dữ liệu ngoài bằng validation/deserialization ở ranh giới nhập dữ liệu. Metadata chỉ giúp mô tả, không làm an toàn thao tác unchecked.

| Nhu cầu | API/giải pháp | Điều cần nhớ |
| --- | --- | --- |
| Biết runtime class của object | `obj.getClass()` | Không khôi phục `List<String>` từ `new ArrayList<String>()` |
| Biết kiểu field đã xóa | `Field.getType()` | Kết quả là `Class<?>` (ví dụ `List.class`) |
| Biết đối số generic khai báo của field | `Field.getGenericType()` + `ParameterizedType` | Phụ thuộc metadata `Signature` hợp lệ |
| Biết bound của class type parameter | `Class.getTypeParameters()` + `TypeVariable.getBounds()` | Là khai báo `T extends ...`, không phải giá trị T của mọi object |
| Biết superclass tham số hóa | `Class.getGenericSuperclass()` | Chỉ có thông tin được ghi trong chữ ký subclass |
| Biết generic return của method | `Method.getGenericReturnType()` | Khác `getReturnType()` ở mức erased |
| Cần truyền `List<String>` qua API | `Type`/`TypeToken`/schema rõ ràng | Không có `List<String>.class` |

## 10. Tự kiểm tra

**Câu 1.** Vì sao `new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass()` cho kết quả `true`?

**Đáp án:** Cả hai cùng kiểu runtime `ArrayList`. `String` và `Integer` ở đối số generic không tạo hai class runtime độc lập.

**Câu 2.** Tại sao `Field.getGenericType()` vẫn trả `List<String>` dù Java xóa kiểu?

**Đáp án:** Reflection đang đọc metadata generic của **khai báo field**, thường được ghi trong `Signature` của class file; nó không đọc một đối số kiểu reified nằm trong mỗi instance.

**Câu 3.** Với `class Box<T extends Number> { T value; }`, `value.getType()` và `value.getGenericType()` trả về gì khi metadata đầy đủ?

**Đáp án:** `getType()` trả `Number.class` theo erasure; `getGenericType()` trả một `TypeVariable` đại diện cho `T`.

**Câu 4.** Nếu công cụ shrinker xóa Signature, có thể dùng `getType()` để chắc chắn dựng lại `List<Map<String, Integer>>` không?

**Đáp án:** Không. Erased descriptor chỉ lưu `List`. Các đối số generic của khai báo nguồn đã bị mất khỏi metadata dùng để tái dựng.

**Câu 5.** Bật `javac -parameters` có bắt buộc để `Field.getGenericType()` đọc `List<String>`?

**Đáp án:** Không. `-parameters` phục vụ tên tham số method/constructor, còn generic type information dùng cơ chế Signature riêng.

**Câu 6.** Một `Class<?>` đã tải thành công có bảo đảm `getGenericSuperclass()` luôn đọc được không?

**Đáp án:** Không. Signature có thể vắng mặt/hỏng hoặc tham chiếu tới kiểu không hiện diện; các API phản chiếu generic có thể trả thông tin ít hơn hoặc ném lỗi thích hợp.

**Kết luận:** Erasure làm cho các object generic thông thường không giữ đối số kiểu riêng tại runtime; generic reflection có thể đọc *khai báo được ghi trong class file*. Khi xây thư viện hay framework, phải biết metadata lấy từ nguồn nào, giới hạn gì và cách ứng xử khi `Signature` không đầy đủ.