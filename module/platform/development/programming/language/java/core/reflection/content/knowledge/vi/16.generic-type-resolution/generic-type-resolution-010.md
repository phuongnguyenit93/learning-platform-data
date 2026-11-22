# Tránh đệ quy vô hạn khi giới hạn kiểu tự tham chiếu trong Java Reflection

Khi phân tích kiểu generic bằng Java Reflection, một biến kiểu có thể xuất hiện **bên trong chính giới hạn (bound) của nó**. Ví dụ quen thuộc nhất là:

```java
class Self<T extends Self<T>> {}

enum State {
    NEW, DONE
}
```

Ở đây, `T` được ràng buộc bởi `Self<T>`. Tương tự, lớp chuẩn Java `Enum` được khai báo theo mẫu `Enum<E extends Enum<E>>`. Các khai báo như vậy hợp lệ và có ích. Chúng thuộc nhóm **F-bounded polymorphism**, cho phép diễn đạt rằng kiểu tham số có quan hệ với chính kiểu đó.

Vấn đề chỉ xuất hiện khi ta tự xây dựng bộ phân tích metadata kiểu:

```text
T -> bound Self<T> -> argument T -> bound Self<T> -> ...
```

Nếu mã cứ gọi `TypeVariable.getBounds()` rồi duyệt `ParameterizedType.getActualTypeArguments()` mà **không phát hiện chu trình**, quá trình phân tích có thể đệ quy vô hạn, gây `StackOverflowError` hoặc tiêu tốn tài nguyên. **Giải pháp là coi cấu trúc generic như đồ thị, nhận diện nút đã nằm trên đường đệ quy hiện tại, và dừng mở rộng chính nút đó.**

## 1. Hiểu đúng giới hạn kiểu tự tham chiếu

Khai báo:

```java
class Self<T extends Self<T>> {}
```

có thể đọc là: một đối số kiểu thay vào `T` phải thỏa ràng buộc là một subtype thích hợp của `Self<T>`. Đây là một quy tắc **ràng buộc kiểu tại compile time**, không yêu cầu `Self` tạo vô hạn đối tượng lúc runtime.

Một ứng dụng điển hình của F-bounds:

```java
abstract class Builder<T extends Builder<T>> {
    abstract T self();

    T label(String text) {
        System.out.println(text);
        return self();
    }
}

final class ReportBuilder extends Builder<ReportBuilder> {
    @Override
    ReportBuilder self() {
        return this;
    }
}
```

Đây là đoạn khai báo minh họa; nó cho phép `label()` trả về kiểu cụ thể `ReportBuilder` khi sử dụng một builder tuân theo mẫu này. Bản thân cú pháp generic không tạo vòng chạy vô hạn.

Trong API chuẩn, `Enum<E extends Enum<E>>` là ví dụ nền tảng: đối số `E` phải liên hệ với kiểu enum cụ thể. Một số ràng buộc cũng xuyên qua interface, wildcard và nhiều biến kiểu; vì vậy chỉ xét trường hợp `T extends T` hoặc chỉ giới hạn một cấp là chưa đủ.

## 2. Các đối tượng `Type` liên quan trong Reflection

`java.lang.reflect.Type` là giao diện gốc để biểu diễn các dạng kiểu. Khi phân giải generic, ta thường gặp:

| Dạng | API Reflection | Ý nghĩa với việc duyệt |
| --- | --- | --- |
| `Class<?>` | `Class`, `isArray()`, `getComponentType()` | Kiểu thông thường hoặc mảng có component là class |
| `TypeVariable<?>` | `getName()`, `getGenericDeclaration()`, `getBounds()` | Biến kiểu `T`, `E`; có thể dẫn trở lại chính nó |
| `ParameterizedType` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` | `List<T>`, `Self<T>`, `Map<K,V>` |
| `WildcardType` | `getUpperBounds()`, `getLowerBounds()` | `? extends X` hoặc `? super X` |
| `GenericArrayType` | `getGenericComponentType()` | `T[]` hoặc mảng có component type generic |

Ví dụ phân tích `Self.class.getTypeParameters()[0]`:

- Kết quả là `TypeVariable<?>` cho `T`.
- `T.getBounds()[0]` là `ParameterizedType` biểu diễn `Self<T>`.
- `getActualTypeArguments()[0]` của `Self<T>` lại là biến kiểu `T`.
- Nếu từ biến kiểu này ta lại gọi `getBounds()`, quá trình quay về `Self<T>` và lặp.

Đây là **chu trình tham chiếu giữa metadata types**, không phải lỗi trong khai báo Java.

Cần phân biệt ba phép đọc: `Class.getTypeParameters()` lấy biến kiểu do class khai báo; `TypeVariable.getBounds()` lấy giới hạn của biến kiểu; `ParameterizedType.getActualTypeArguments()` lấy đối số kiểu trong một kiểu đã tham số hóa. Việc nối ba API có thể vô tình quay lại nút cũ.

## 3. Tại sao cách duyệt đệ quy ngây thơ thất bại?

Ví dụ sau minh họa **thuật toán sai** (không chạy độc lập và không nên dùng trong ứng dụng):

```java
static void brokenWalk(Type type) {
    if (type instanceof TypeVariable<?> variable) {
        for (Type bound : variable.getBounds()) {
            brokenWalk(bound);
        }
    } else if (type instanceof ParameterizedType parameterized) {
        for (Type argument : parameterized.getActualTypeArguments()) {
            brokenWalk(argument);
        }
    }
}
```

Đường đi với `T extends Self<T>`:

```text
TypeVariable T
    |
    v
ParameterizedType Self<T>
    |
    v
Actual type argument: TypeVariable T
    |
    v
Bound: ParameterizedType Self<T>
    |
    v
Actual type argument: TypeVariable T
    ... (lặp lại)
```

Nếu không có điểm dừng, mỗi lần thăm `T` lại tạo thêm một lần đệ quy vào bound. Với đủ lần lặp, chương trình có thể ném `StackOverflowError`. Không nên thử tạo một lần chạy thật sự đến lỗi stack overflow để kiểm chứng; đồ thị đã cho thấy chu trình.

**Cấm suy luận sai:** `T.getBounds()` không có lời hứa rằng kết quả sẽ là tập kiểu không chứa đường dẫn quay về `T`. Generic bounds hợp lệ hoàn toàn có thể tự tham chiếu hoặc tham chiếu qua các kiểu trung gian.

## 4. Cốt lõi giải pháp: theo dõi đường đệ quy đang hoạt động

Đối với một cây thuần túy, ta có thể duyệt các nút con mà không cần nhớ những nút đã gặp. Đối với **đồ thị có chu trình**, cần theo dõi đường đi.

Thuật toán DFS an toàn:

1. Nhận một `Type` và bộ `active` chứa các `Type` **đang nằm trên nhánh đệ quy hiện tại**.
2. Nếu `type` đã có trong `active`, in/chú thích một chu trình và **không duyệt tiếp** từ nút này.
3. Nếu chưa có, thêm vào `active` rồi xử lý children theo loại `Type`.
4. Sau khi xử lý xong children, xóa `type` khỏi `active` trong `finally`.

Pseudocode:

```text
visit(type, active):
    if type in active:
        emit "[cycle]"
        return

    active.add(type)
    try:
        emit type
        for each child of type:
            visit(child, active)
    finally:
        active.remove(type)
```

Điểm quan trọng là **phải xóa khi rời nhánh**. Khi một kiểu hợp lệ xuất hiện ở hai nhánh khác nhau, ta có thể muốn hiển thị kiểu đó ở cả hai nơi. Cờ chu trình cần phát hiện sự lặp **trên cùng đường đi**, không mặc định xóa mọi lần xuất hiện sau này trong toàn bộ đồ thị.

Đối với một công cụ chỉ muốn liệt kê mỗi kiểu đúng một lần, tập `visited` toàn cục cũng hữu ích. Nhưng cần phân biệt rõ: **`active` phát hiện chu trình**, còn **`visited` toàn cục phát hiện mọi sự thăm lại**. Dùng `visited` toàn cục cho kết quả dạng cây có thể làm mất thông tin của một nhánh hợp lệ.

## 5. Ví dụ Java 17+ đầy đủ: duyệt `Type` và đánh dấu chu trình

Chương trình sau duyệt các dạng `TypeVariable`, `ParameterizedType`, `WildcardType`, `GenericArrayType` và `Class` dạng mảng. Để output dễ đọc, ví dụ chỉ in tên ngắn của raw class trong `ParameterizedType`; không đi vào toàn bộ các method/field của raw class.

Lưu nội dung vào `GenericCycleDemo.java`:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.HashSet;
import java.util.Set;

public class GenericCycleDemo {

    static class Self<T extends Self<T>> {}

    static class Ranked<T extends Comparable<? super T>> {}

    static class Arrays<T extends Comparable<T>> {
        T[] values;
    }

    static void walk(Type type, int depth, Set<Type> active) {
        String indent = "  ".repeat(depth);

        if (!active.add(type)) {
            System.out.println(indent + "CYCLE -> " + label(type));
            return;
        }

        System.out.println(indent + label(type));

        try {
            if (type instanceof TypeVariable<?> variable) {
                for (Type bound : variable.getBounds()) {
                    walk(bound, depth + 1, active);
                }
            } else if (type instanceof ParameterizedType parameterized) {
                for (Type argument : parameterized.getActualTypeArguments()) {
                    walk(argument, depth + 1, active);
                }
            } else if (type instanceof WildcardType wildcard) {
                for (Type bound : wildcard.getUpperBounds()) {
                    walk(bound, depth + 1, active);
                }
                for (Type bound : wildcard.getLowerBounds()) {
                    walk(bound, depth + 1, active);
                }
            } else if (type instanceof GenericArrayType array) {
                walk(array.getGenericComponentType(), depth + 1, active);
            } else if (type instanceof Class<?> clazz && clazz.isArray()) {
                walk(clazz.getComponentType(), depth + 1, active);
            }
        } finally {
            active.remove(type);
        }
    }

    static String label(Type type) {
        if (type instanceof TypeVariable<?> variable) {
            return "variable " + variable.getName();
        }
        if (type instanceof ParameterizedType parameterized) {
            Type raw = parameterized.getRawType();
            String name = raw instanceof Class<?> clazz
                    ? clazz.getSimpleName() : raw.getTypeName();
            return "parameterized " + name;
        }
        if (type instanceof WildcardType) {
            return "wildcard ?";
        }
        if (type instanceof GenericArrayType) {
            return "generic array []";
        }
        return "class " + type.getTypeName();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Self:");
        walk(Self.class.getTypeParameters()[0], 0, new HashSet<>());

        System.out.println("Ranked:");
        walk(Ranked.class.getTypeParameters()[0], 0, new HashSet<>());

        System.out.println("Arrays:");
        walk(Arrays.class.getDeclaredField("values").getGenericType(),
                0, new HashSet<>());

        System.out.println("Enum:");
        walk(Enum.class.getTypeParameters()[0], 0, new HashSet<>());
    }
}
```

Lệnh:

```bash
javac GenericCycleDemo.java
java GenericCycleDemo
```

Đầu ra (Java 17+):

```text
Self:
variable T
  parameterized Self
    CYCLE -> variable T
Ranked:
variable T
  parameterized Comparable
    wildcard ?
      class java.lang.Object
      CYCLE -> variable T
Arrays:
generic array []
  variable T
    parameterized Comparable
      CYCLE -> variable T
Enum:
variable E
  parameterized Enum
    CYCLE -> variable E
```

Giải thích:

- **Self:** `T` có bound `Self<T>`. Khi vào đối số kiểu `T` lần thứ hai trên cùng đường đệ quy, chương trình in `CYCLE -> variable T` rồi dừng.
- **Ranked:** `T extends Comparable<? super T>` dẫn qua `ParameterizedType`, sau đó `WildcardType`, rồi quay lại `T`. Wildcard có upper bound mặc định `Object`, đồng thời lower bound là `T`.
- **Arrays:** trường `T[] values` được thể hiện bằng `GenericArrayType`; component `T` dẫn tiếp tới bound `Comparable<T>`, sau đó quay lại `T`.
- **Enum:** `E extends Enum<E>` trong API chuẩn Java cũng có chu trình hợp lệ. Bộ phân tích dừng ở lần quay lại `E`.

Với ví dụ này, **mọi đường duyệt đều kết thúc** mà không cần giới hạn độ sâu tùy tiện.

## 6. Vì sao dùng `Set<Type>` và không chỉ `Set<String>`?

Một biến kiểu tên `T` không có danh tính duy nhất trên toàn ứng dụng:

```java
class Box<T> {}

class Other<T> {}

class Service {
    <T> void execute(T value) {}
}
```

Cả ba có thể có biến tên `T`, nhưng được khai báo ở **những generic declaration khác nhau**. Nếu dùng `HashSet<String>` chứa tên `"T"`, bộ phân tích sẽ coi các biến không liên quan là một nút duy nhất.

Thay vào đó, dùng `TypeVariable<?>` và các đối tượng `Type` đúng nghĩa. `TypeVariable.getGenericDeclaration()` xác định khai báo sở hữu biến kiểu: `Class`, `Method` hoặc `Constructor`. Theo hợp đồng `TypeVariable`, nhiều đối tượng runtime có thể đại diện cùng một biến kiểu; chúng phải được xem là tương đương theo khai báo và tên. Vì vậy, với các implementation Reflection chuẩn, `HashSet<Type>` sử dụng `equals()/hashCode()` là lựa chọn phù hợp để nhận diện nút.

**Không chỉ dựa vào `==` hoặc `IdentityHashMap`** cho thuật toán này: API không bảo đảm mọi lần lấy metadata của cùng một biến kiểu đều trả về đúng một object identity. Nếu reflection tái tạo wrapper tương đương, so sánh tham chiếu có thể bỏ sót chu trình.

Nếu cần hiển thị danh tính để debug, có thể in cả:

```java
TypeVariable<?> variable = Self.class.getTypeParameters()[0];
System.out.println(variable.getName());
System.out.println(variable.getGenericDeclaration());
```

Đây là đoạn minh họa sử dụng class `Self` từ chương trình chính. `getGenericDeclaration()` giúp phân biệt hai `T` cùng tên từ hai nơi khai báo khác nhau, còn kết quả duyệt vẫn cần cơ chế `active`.

## 7. Vì sao `active` phải được quản lý theo nhánh?

Xét một cấu trúc generic có hai nhánh cùng tham chiếu một biến kiểu nhưng không tạo chu trình trên từng nhánh. Ví dụ về mặt cấu trúc:

```text
ParameterizedType Pair<T, T>
                /      \
               T        T
```

Nếu dùng một tập `visited` toàn cục rồi không xóa sau nhánh đầu tiên, nhánh thứ hai có thể bị in nhầm là đã xử lý hoặc bị bỏ qua. Với `active` và `finally { active.remove(type); }`, mỗi nhánh độc lập có thể hiển thị `T`, trong khi bất kỳ nhánh nào tự quay lại `T` qua giới hạn generic sẽ vẫn được gắn nhãn `CYCLE`.

Trong ứng dụng thực tế thường có hai nhu cầu:

| Mục tiêu | Dữ liệu theo dõi | Kết quả |
| --- | --- | --- |
| In cây giải thích từng nhánh | Tập `active` cho đường DFS | Gặp lại trên cùng đường: cycle; gặp ở nhánh khác: có thể in lại |
| Lập chỉ mục mỗi kiểu một lần | Tập `visited` toàn cục, có thể kèm `active` | Mỗi nút xử lý một lần; cần đánh dấu rõ cycle và repeated reference |
| Tránh tài nguyên quá mức | Đếm nút / giới hạn độ sâu độc lập | Chặn cây quá lớn, kể cả không có cycle |

Nếu chỉ cần suy ra một tính chất kiểu dạng boolean, có thể dùng memoization để tránh tính lại. Nhưng memoization cho thuật toán trên đồ thị có chu trình đòi hỏi phân biệt trạng thái **đang xử lý** và **đã hoàn tất**, vì khi quay lại một nút chưa hoàn tất, giá trị của nút đó có thể chưa được xác định.

## 8. Đường đi phức tạp: wildcard, mảng, nhiều giới hạn và owner type

Chu trình không phải lúc nào cũng có dạng thẳng `T -> Self<T> -> T`.

### Wildcard

```java
class Ranked<T extends Comparable<? super T>> {}
```

Đường duyệt:

```text
T
  -> Comparable<? super T>
       -> WildcardType (? super T)
            -> lower bound T
                 -> cycle
```

Nếu bộ duyệt xử lý `TypeVariable` và `ParameterizedType` mà bỏ qua `WildcardType.getLowerBounds()`, nó có thể không phát hiện đường chu trình này khi cần phân tích đầy đủ cấu trúc.

### Generic array

```java
class Arrays<T extends Comparable<T>> {
    T[] values;
}
```

`Field.getGenericType()` trên `values` trả về `GenericArrayType` với component `T`. Nếu tiếp tục mở bounds của `T`, ta gặp `Comparable<T>` và vòng tham chiếu. Vì vậy cần xử lý `getGenericComponentType()`; còn với `Class<?>` đại diện kiểu mảng cụ thể như `String[]` thì dùng `Class.getComponentType()`.

### Multiple bounds

```java
class Multi<T extends Comparable<T> & java.io.Serializable> {}
```

`TypeVariable.getBounds()` trả mảng các giới hạn. Bound `Comparable<T>` có đường quay về `T`, còn bound `Serializable` là nhánh riêng không có chu trình. Dùng `active` theo nhánh giúp duyệt được cả hai và không đánh dấu nhầm `Serializable`.

### Owner type của generic nested class

`ParameterizedType.getOwnerType()` có thể chứa kiểu chủ sở hữu của một inner/nested declaration. Chương trình mẫu tập trung vào đường recursion ở **type arguments/bounds** nên không tự đi qua owner type. Nếu xây dựng **bộ duyệt mọi cạnh của đồ thị kiểu**, hãy kiểm tra `getOwnerType() != null` và gọi `walk(owner, ...)` qua **cùng tập `active`**, đúng quy tắc chống chu trình.

Không nên gọi tất cả API Reflection không liên quan đến cấu trúc generic, chẳng hạn duyệt mọi method/field của `Class` từ một `ParameterizedType`, trừ khi bài toán thực sự yêu cầu. Việc mở rộng đồ thị vô ý vừa tăng số nút vừa dễ sinh chu trình không cần thiết.

## 9. Hai cách phòng vệ bổ sung: giới hạn độ sâu và ngân sách nút

Phát hiện chu trình bằng `active` giải quyết **đường quay lại nút cũ**, nhưng một đồ thị rất sâu hoặc quá lớn vẫn có thể gây vấn đề hiệu năng và bộ nhớ, dù không có cycle. Với công cụ đọc generic từ plugin hoặc thư viện lạ, nên cân nhắc:

- `maxDepth`: từ chối duyệt sâu hơn mức được cấu hình; thông báo rõ `[max depth reached]`.
- `maxNodes`: đếm lượng nút đã ghé qua và ngừng nếu vượt ngân sách; thông báo `[node budget exceeded]`.
- Cache/memoization: nếu tính lại cùng một kiểu qua nhiều nhánh tốn kém, có thể lưu kết quả đã hoàn tất.
- Kiểm tra dữ liệu từ implementation `Type` tùy chỉnh: chỉ sử dụng giả định `equals()/hashCode()` đúng hợp đồng; tránh gọi `toString()` phức tạp không kiểm soát nếu object do thư viện cung cấp.

**Không dùng `maxDepth` làm cách duy nhất phát hiện cycle.** Nếu cutoff ở độ sâu 10, nó chỉ che chu trình sau mười bước và còn có thể cắt bỏ cấu trúc generic hợp lệ. Nên có cả cơ chế nhận diện chu trình và giới hạn tài nguyên độc lập, với dấu hiệu dừng khác nhau để người dùng hiểu vì sao dữ liệu bị rút gọn.

Ngoài ra, đừng nuốt `StackOverflowError` để làm tín hiệu dừng. Khi đó stack đã cạn, và lỗi có thể đến từ vấn đề khác. Phát hiện chu trình **trước khi** gọi đệ quy mới là cách tiếp cận đúng.

## 10. Các lỗi thường gặp khi viết bộ phân giải generic

**Lỗi 1 — Coi generic metadata là cây.** Việc một `TypeVariable` xuất hiện lại trong bounds tạo đồ thị có chu trình. Dùng DFS với tập `active`, không duyệt mù.

**Lỗi 2 — Kiểm tra chỉ bằng tên biến kiểu.** Hai biến `T` trong hai class/method khác nhau có tên trùng nhưng không cùng nút. Dùng danh tính ngữ nghĩa theo `TypeVariable` và `GenericDeclaration`.

**Lỗi 3 — So sánh chỉ bằng object identity.** Reflection có thể trả các object `TypeVariable` tương đương nhưng không phải cùng tham chiếu. Với implementation chuẩn, dùng `equals()/hashCode()`.

**Lỗi 4 — Không dọn `active` khi thoát.** Nếu thiếu `finally`, ngoại lệ khi duyệt một nhánh có thể để lại trạng thái sai, hoặc kiểu dùng ở nhánh khác bị đánh dấu nhầm. Chỉ xóa khi chính lần gọi này đã thêm nút thành công.

**Lỗi 5 — Bỏ sót các cạnh `WildcardType` / `GenericArrayType`.** Chu trình có thể đi qua `? super T`, `? extends T` và component array. Muốn phân tích đầy đủ thì phải duyệt các edges liên quan.

**Lỗi 6 — Hiểu `getBounds()` là danh sách superclass thuần túy.** Bounds có thể là interface, parameterized type, nhiều giới hạn, hoặc `Object` khi biến không khai báo bound tường minh. Mỗi phần tử là `Type`, cần phân nhánh theo runtime interface của nó.

**Lỗi 7 — Dùng `ParameterizedType.getRawType()` như đã phân giải đầy đủ.** `Self<T>` có raw type là `Self`, nhưng chu trình nằm trong **actual type argument `T`**. Chỉ lấy raw class sẽ bỏ qua thông tin generic.

**Lỗi 8 — Tự thay `T` bằng `Self<T>` không có điểm dừng.** Một thuật toán substitution phải có quy tắc xử lý biến kiểu đang phân giải (ví dụ giữ tham chiếu, đánh dấu deferred hoặc trả cấu trúc chu trình) thay vì thay thế mãi. Không thể mong tự mở rộng thành một biểu thức hữu hạn với vô số `Self<Self<...>>`.

## 11. Dùng trong ứng dụng: resolver, schema generator và serializer

Các công cụ như object mapper, dependency injection framework, schema generator hoặc trình tạo tài liệu API thường phải đọc những cấu trúc kiểu phức tạp. Một class theo mẫu `Node<N extends Node<N>>` không hiếm. Nếu generator tạo schema đệ quy không kiểm soát, nó có thể lặp vô hạn hoặc tạo JSON schema khổng lồ.

Một chiến lược rõ ràng là:

1. **Phân biệt tham chiếu với khai triển:** Khi gặp lại biến kiểu đang xử lý, tạo một dấu tham chiếu ổn định như `TypeVariable(T, declaringElement)` thay vì mở lại bounds.
2. **Xử lý các kiểu theo cấu trúc:** Duyệt `TypeVariable`, arguments của `ParameterizedType`, upper/lower bounds của `WildcardType` và component của `GenericArrayType`.
3. **Ghi nhận cycle có chủ đích:** Trong trình hiển thị có thể in `[cycle]`; trong schema có thể dùng tham chiếu schema phù hợp để bảo toàn cấu trúc.
4. **Tôn trọng scope khai báo:** Hai `T` thuộc hai class khác nhau không được gộp thành một nút schema vì trùng tên.
5. **Giới hạn tài nguyên độc lập:** Cung cấp cảnh báo khi vượt độ sâu hoặc ngân sách, tránh trả kết quả trông như đầy đủ dù đã bị cắt.

Nếu mục tiêu là kiểm tra một bound cụ thể, đôi khi không cần duyệt toàn bộ đồ thị. Ví dụ kiểm tra raw bound `Comparable` có thể đọc `ParameterizedType.getRawType()` rồi dừng; nếu cần đối số `T` thì mở rộng có kiểm soát. Tối giản phạm vi duyệt giúp tránh công việc thừa.

## 12. Câu hỏi tự kiểm tra

**1. Vì sao `Enum<E extends Enum<E>>` không gây lỗi compile, nhưng có thể làm mã Reflection duyệt sai bị vô hạn?**

Vì khai báo F-bound hợp lệ; lỗi xảy ra khi một thuật toán metadata liên tục đi từ `E` đến `Enum<E>` rồi trở lại `E` mà không nhận diện chu trình.

**2. Dùng `Set<String> seenNames` với mỗi tên `"T"` để chống cycle đã đủ chưa?**

Chưa. Biến `T` của hai generic declarations khác nhau là hai biến độc lập. Cần dùng `Type` với semantics nhận diện phù hợp, hoặc khóa gồm khai báo và tên.

**3. Vì sao code cần `active.remove(type)` trong `finally`?**

Để nhánh duyệt sau không kế thừa trạng thái của nhánh trước và để dọn trạng thái ngay cả khi xử lý children ném exception. Khi một nút lặp lại trên cùng nhánh, ta phát hiện cycle và return **trước khi thêm lần nữa**, nên không được xóa nhầm nút của ancestor.

**4. Với `T extends Comparable<? super T>`, cần theo dõi những loại `Type` nào để thấy chu trình?**

`TypeVariable` của `T` → `ParameterizedType` của `Comparable<? super T>` → `WildcardType` của `? super T` → lower bound là `T`.

**5. Vì sao cutoff độ sâu 10 không phải lời giải hoàn chỉnh?**

Vì nó có thể cắt bỏ một cấu trúc không có cycle nhưng sâu hơn 10; đồng thời không cho biết điểm nào thật sự trùng lặp. Giới hạn tài nguyên nên kết hợp với cycle detection.

## Ghi nhớ

- F-bounded generics như `T extends Self<T>` và `E extends Enum<E>` là **hợp lệ**.
- `TypeVariable.getBounds()` và `ParameterizedType.getActualTypeArguments()` có thể dẫn vòng qua cùng một biến kiểu.
- **Duyệt `Type` như đồ thị:** phát hiện một kiểu đã có trên đường đệ quy hiện tại, đánh dấu `CYCLE` và ngừng mở rộng nhánh đó.
- **Dùng `Set<Type> active`**, so sánh theo ngữ nghĩa `equals/hashCode` của Reflection types; dọn tập khi rời nhánh bằng `finally`.
- Kiểm tra cả `WildcardType`, `GenericArrayType` và các cạnh liên quan; đặt thêm giới hạn độ sâu và số nút khi cần để bảo vệ tài nguyên.
- Không thay thế F-bounds một cách vô hạn; nếu cần mô hình hóa, hãy giữ tham chiếu tới biến kiểu hay nút schema đã biết.

Điểm mấu chốt là **bản thân kiểu tự tham chiếu không sai; thuật toán mở rộng metadata không nhận diện chu trình mới là vấn đề**.
