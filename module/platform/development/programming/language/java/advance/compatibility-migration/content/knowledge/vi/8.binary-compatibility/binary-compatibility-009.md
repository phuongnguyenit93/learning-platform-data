# Type erasure, bridge method và thay đổi API dùng generics

Java generics giúp compiler kiểm tra kiểu dữ liệu trước khi chương trình chạy. Tuy nhiên, ở cấp class file, phần lớn thông tin về đối số kiểu như `String`, `Integer` hay `Customer` không trở thành các kiểu runtime độc lập. Compiler áp dụng **type erasure**, chèn cast khi cần và đôi khi tạo **bridge method** để bảo toàn hành vi overriding sau khi kiểu generic được xóa.

Điều này tạo ra một đặc điểm quan trọng của Java compatibility migration: **một thay đổi trông nhỏ trong khai báo generic có thể giữ nguyên hoặc phá vỡ hợp đồng nhị phân, tùy nó có làm thay đổi tên, descriptor hay quan hệ kế thừa của method hay không**. Ngược lại, một thay đổi có cùng descriptor sau erasure vẫn có thể làm source cũ không compile hoặc làm hành vi runtime khác trước.

Bài học này giải thích cách `javac` chuyển generic source thành bytecode, vì sao bridge method xuất hiện, cách phân biệt `Signature` metadata với JVM method descriptor và cách đánh giá rủi ro khi nâng JDK, thư viện, framework hoặc sửa API dùng generics.

## 1. Bốn lớp hợp đồng cần phân biệt

Khi đánh giá một API generic, không nên chỉ nhìn khai báo Java trong IDE. Cần xem ít nhất bốn lớp:

| Lớp hợp đồng | Ý nghĩa | Ví dụ |
|---|---|---|
| Source API | Cách compiler nhìn type parameter, type argument, bound và overload | `List<String>` hoặc `<T extends Number> T get()` |
| Erased API | Những kiểu còn lại sau khi xóa type parameter | `List` hoặc `Number get()` |
| Binary descriptor | Tên và kiểu tham số/trả về mà JVM dùng để liên kết method | `(Ljava/lang/Number;)Ljava/lang/Number;` |
| Runtime behavior | Cast, dispatch, reflection và cách thư viện xử lý dữ liệu | `ClassCastException` hoặc `AbstractMethodError` |

**Source compatibility** hỏi liệu source của consumer cũ có còn compile với version API mới hay không. **Binary compatibility** hỏi liệu bytecode consumer đã compile từ trước có còn liên kết và chạy với version thư viện mới hay không. **Behavioral compatibility** hỏi liệu kết quả, exception, serialization và các side effect có giữ đúng hợp đồng hay không.

Ba khái niệm này không thay thế nhau. Một API có thể binary-compatible nhưng source-incompatible; hoặc cả hai đều hợp lệ mà logic nghiệp vụ vẫn thay đổi.

## 2. Type erasure hoạt động như thế nào?

### 2.1. Erasure của type parameter không có bound

Với class:

```java
public class Box<T> {
    private T value;

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Nếu `T` không có upper bound tường minh, erasure của `T` là `Object`. Mô hình bytecode tương đương về mặt kiểu có dạng:

```java
public class Box {
    private Object value;

    public Object get() {
        return value;
    }

    public void set(Object value) {
        this.value = value;
    }
}
```

Đây là cách diễn giải để hiểu erasure, không phải file source Java mà compiler thực sự xuất ra. Class file vẫn có thể lưu generic `Signature` metadata để compiler khác và reflection API đọc được khai báo generic ban đầu.

Khi client viết:

```java
Box<String> box = new Box<>();
box.set("Java");
String text = box.get();
```

compiler biết `box.get()` có kết quả kiểu `String` theo generic source API, nhưng method runtime trả về `Object`. Vì vậy bytecode của client có thể chứa thao tác `checkcast java/lang/String` trước khi gán kết quả cho biến `String`.

### 2.2. Erasure của type parameter có bound

Khi type parameter có upper bound, erasure được xác định bởi bound đầu tiên:

```java
public class NumericBox<T extends Number> {
    private T value;

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Vì `T extends Number`, các method ở mức bytecode có dạng:

```text
get()Ljava/lang/Number;
set(Ljava/lang/Number;)V
```

Nó không còn là `Object` như `Box<T>` không có bound. Đây là nguyên nhân đổi generic bound có thể là breaking change thực sự.

Với multiple bounds:

```java
class Key<T extends Comparable<T> & java.io.Serializable> {
    T copy(T key) {
        return key;
    }
}
```

Erasure của `T` là `Comparable` vì đó là bound đầu tiên. Đổi thứ tự hai interface bound sang `Serializable & Comparable<T>` có thể đổi erasure thành `Serializable`. Dù tập ràng buộc ở source có vẻ tương tự, JVM method descriptor có thể thay đổi.

### 2.3. Erasure của parameterized type

`List<String>` và `List<Integer>` đều có erasure là `List`. Tương tự:

| Khai báo source | Erasure |
|---|---|
| `List<String>` | `List` |
| `Map<String, Customer>` | `Map` |
| `T` không có upper bound | `Object` |
| `T extends Number` | `Number` |
| `T extends Serializable & Cloneable` | `Serializable` |
| `List<? extends Number>` | `List` |

Các đối số kiểu của generic thường không được lưu như tham số runtime trong JVM descriptor. Đây là lý do `List<String>` và `List<Integer>` không thể dùng để định nghĩa hai overload chỉ khác nhau ở type argument.

### 2.4. Hệ quả khi dùng generics

Những giới hạn quen thuộc của Java generics bắt nguồn từ việc phần lớn type argument không được reify thành kiểu runtime riêng:

- Không thể viết `new T()` nếu không có một factory, constructor reference hoặc `Class<T>` phù hợp.
- Không thể dùng `T.class`.
- Không thể tạo trực tiếp `new T[10]`.
- Không thể kiểm tra `instanceof List<String>`; dạng `List<?>` có thể dùng trong ngữ cảnh phù hợp.
- Không thể overload hai method chỉ khác `List<String>` và `List<Integer>`.
- Raw type và unchecked cast có thể làm lỗi kiểu chỉ xuất hiện khi runtime thực hiện cast.

Generics có thể chứa thông tin bổ sung trong class-file attribute, nhưng JVM không tự áp dụng type argument `String` hoặc `Integer` vào mọi thao tác runtime.

## 3. JVM descriptor khác với generic Signature metadata

Một class file có thể lưu cùng lúc **descriptor** và **Signature attribute**. Hai loại thông tin phục vụ mục đích khác nhau.

Xét method:

```java
public java.util.List<String> findAll() {
    return java.util.List.of("A", "B");
}
```

Ở mức class file, method descriptor chỉ phản ánh `List`:

```text
descriptor: ()Ljava/util/List;
```

Generic Signature có thể lưu thêm type argument:

```text
Signature: ()Ljava/util/List<Ljava/lang/String;>;
```

Descriptor được JVM dùng khi liên kết method. `Signature` metadata được compiler và reflection API dùng để biểu diễn thông tin generic ở mức source; nó không làm JVM coi `List<String>` là một runtime class độc lập với `List<Integer>`.

Điều này dẫn đến hai trường hợp cần phân biệt:

1. Đổi `List<String> findAll()` thành `List<Integer> findAll()` thường giữ nguyên descriptor `()Ljava/util/List;`. Bytecode cũ có thể tiếp tục liên kết, nhưng consumer source khi compile lại và các xử lý runtime có thể bị ảnh hưởng.
2. Đổi `T get()` từ `T` không bound sang `T extends Number` đổi descriptor từ `()Ljava/lang/Object;` sang `()Ljava/lang/Number;`. Đây có thể phá binary compatibility.

Để quan sát hai lớp thông tin:

```bash
javap -classpath build/classes -p -s com.example.Box
javap -classpath build/classes -p -v com.example.Box
```

Tùy version compiler và class, `-s` hiển thị descriptor; `-v` hiển thị constant pool, `Signature`, flags và metadata bổ sung. Cần nhìn đúng class file của artifact được phát hành, không chỉ source trong IDE.

## 4. Vì sao compiler phải tạo bridge method?

### 4.1. Vấn đề sau erasure: method override có descriptor khác

Xét superclass generic:

```java
public class Node<T> {
    private T data;

    public void setData(T data) {
        this.data = data;
    }

    public T getData() {
        return data;
    }
}
```

Subclass dùng kiểu cụ thể:

```java
public class MyNode extends Node<Integer> {
    @Override
    public void setData(Integer data) {
        super.setData(data);
    }

    @Override
    public Integer getData() {
        return super.getData();
    }
}
```

Trong hệ thống type của Java source, `MyNode.setData(Integer)` là override hợp lệ của `Node<Integer>.setData(Integer)`. Nhưng sau erasure, phương thức khai báo trong `Node` có parameter `Object`, còn phương thức trong `MyNode` có parameter `Integer`.

Các method descriptor tương ứng là:

```text
Node.setData(Ljava/lang/Object;)V
MyNode.setData(Ljava/lang/Integer;)V

Node.getData()Ljava/lang/Object;
MyNode.getData()Ljava/lang/Integer;
```

Nếu không có cơ chế bổ sung, JVM có thể không dispatch lời gọi cũ tới implementation override mà source code yêu cầu. Compiler giải quyết sự chênh lệch đó bằng bridge method.

### 4.2. Bridge method do compiler sinh

Về mặt ý tưởng, compiler tạo thêm các method trong `MyNode` giống như:

```java
// Mô phỏng logic bridge, không phải source cần tự viết.
public void setData(Object data) {
    setData((Integer) data);
}

public Object getData() {
    return getData();
}
```

Ví dụ trên chỉ diễn giải luồng chuyển tiếp; source Java thông thường không thể sao chép nguyên xi mọi bridge cùng method trả về khác nhau vì quy tắc source signature. Compiler tạo bridge trực tiếp ở cấp bytecode.

Bridge `setData(Object)` thực hiện cast sang `Integer` và gọi `setData(Integer)`. Bridge `getData():Object` gọi method có kiểu trả về `Integer`, rồi trả kết quả dưới kiểu `Object`. Nhờ đó binary tham chiếu descriptor đã erased của superclass vẫn dispatch tới subclass.

Với bridge từ covariant return type, JVM có thể cần hai method có cùng tên và parameter descriptor nhưng return descriptor khác nhau. Java source không cho khai báo overload chỉ khác return type, nhưng class file có thể chứa các method bridge được compiler tạo để duy trì đúng liên kết.

### 4.3. Bridge là method thật trong class file

Bridge method không chỉ là khái niệm của compiler. Nó được phát hành như method trong `.class` và thường có flags:

```text
ACC_PUBLIC
ACC_BRIDGE
ACC_SYNTHETIC
```

Các flags chính xác phụ thuộc visibility và trường hợp cụ thể. Dùng:

```bash
javap -classpath build/classes -p -c -s -v com.example.MyNode
```

để quan sát method, descriptor, bytecode cast/delegate và flags. Trong Java reflection, `Method.isBridge()` và `Method.isSynthetic()` giúp nhận diện bridge.

Điểm quan trọng đối với migration: **bridge là một phần của binary mà các client đã biên dịch có thể đang phụ thuộc**. Nếu quá trình build, instrumentation, bytecode shading, minimization hoặc thay đổi hierarchy vô tình loại bỏ bridge cần thiết, consumer có thể bị lỗi linkage hoặc dispatch sai.

### 4.4. Cast trong bridge có thể làm lộ lỗi raw type

Ví dụ:

```java
MyNode myNode = new MyNode();
Node raw = myNode; // raw type

raw.setData("text");
```

Compiler có thể cảnh báo raw/unchecked usage nhưng vẫn cho phép lời gọi. Bytecode gọi method `Node.setData(Object)`. JVM dispatch tới bridge tương ứng trong `MyNode`, bridge cast `String` thành `Integer` và ném `ClassCastException`.

Lỗi không chứng minh bridge hoạt động sai. Bridge đang bảo vệ hợp đồng kiểu của `MyNode` ở runtime theo cách tốt nhất có thể sau khi type argument bị xóa. Gốc vấn đề là một client đã bỏ qua generic type safety.

Không nên thêm `@SuppressWarnings("unchecked")` để che vấn đề nếu dữ liệu không thật sự có kiểu như cam kết.

## 5. Bridge method không chỉ xuất hiện vì generic parameter

Một trường hợp khác tạo bridge là **covariant return type**: class con override method nhưng trả về kiểu con cụ thể hơn.

```java
class Animal {
}

class Dog extends Animal {
}

class AnimalFactory {
    public Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    public Dog create() {
        return new Dog();
    }
}
```

Trong Java source, `DogFactory.create():Dog` override hợp lệ `AnimalFactory.create():Animal`. Ở JVM, return type là một phần của method descriptor. Compiler có thể sinh bridge `create():Animal` để lời gọi biên dịch theo superclass vẫn dispatch đúng đến `create():Dog`.

Đây là ví dụ không cần type parameter. Nó giúp phân biệt hai ý:

- Type erasure là cơ chế chung của generics.
- Bridge method là giải pháp compiler sử dụng khi cần bảo toàn override/dispatch sau erasure hoặc khi có covariant return.

Không nên xem mọi synthetic method đều là bridge generic; nhiều công cụ khác cũng tạo synthetic method hoặc bytecode hỗ trợ.

## 6. Thay đổi API generic nào giữ descriptor, thay đổi nào phá descriptor?

### 6.1. Chỉ đổi đối số kiểu của collection

API v1:

```java
public List<String> names();
```

API v2:

```java
public List<CharSequence> names();
```

Cả hai có erased return type `List`. Descriptor vẫn là:

```text
()Ljava/util/List;
```

Do đó một binary cũ thường vẫn liên kết được nếu class/method, visibility, hierarchy và các điều kiện khác giữ nguyên. Nhưng source consumer cũ:

```java
List<String> values = api.names();
```

có thể không compile với v2 vì `List<CharSequence>` không thể gán cho `List<String>`. Generics trong Java là invariant đối với type argument thông thường.

Ngay cả khi chỉ thay `List<String>` bằng `List<Integer>` và binary cũ vẫn liên kết, code cũ có thể lấy phần tử rồi cast sang `String`, dẫn tới `ClassCastException` nếu thư viện mới trả `Integer`.

**Không đổi descriptor** không có nghĩa là **không đổi hợp đồng source hoặc hành vi**.

### 6.2. Đổi upper bound làm thay đổi erasure

API v1:

```java
public class Identity<T> {
    public T echo(T value) {
        return value;
    }
}
```

Method v1 sau erasure:

```text
echo(Ljava/lang/Object;)Ljava/lang/Object;
```

API v2:

```java
public class Identity<T extends Number> {
    public T echo(T value) {
        return value;
    }
}
```

Method v2 sau erasure:

```text
echo(Ljava/lang/Number;)Ljava/lang/Number;
```

Client v1 đã compile tham chiếu descriptor `echo(Object):Object`. Nếu chạy binary đó với thư viện v2 chỉ còn `echo(Number):Number`, JVM không tự chọn method mới theo khả năng gán kiểu; binary có thể ném `NoSuchMethodError`.

Đây là một breaking change nhị phân, dù tên class và tên method đều không đổi.

### 6.3. Đổi bound nhưng erased descriptor có thể không đổi

Không phải mọi thay đổi bound đều đổi descriptor. Ví dụ:

```java
public class Store<T> {
    public void add(List<T> items) {
    }
}
```

Thay `T` thành `T extends Number`, method vẫn nhận `List` ở mức descriptor:

```text
add(Ljava/util/List;)V
```

Tuy nhiên, generic `Signature` metadata và những kiểu mà consumer được phép truyền đã thay đổi. Vì vậy vẫn cần kiểm tra source compatibility và runtime behavior.

Cần đánh giá **erasure tại từng vị trí trong descriptor**, thay vì kết luận mọi bound change đều phá binary compatibility hoặc mọi generic change đều an toàn.

### 6.4. Thứ tự multiple bounds có thể ảnh hưởng ABI

API v1:

```java
class KeyStore<T extends Comparable<T> & java.io.Serializable> {
    public T normalize(T key) {
        return key;
    }
}
```

Erasure của `T` là `Comparable`. Nếu sửa thành:

```java
class KeyStore<T extends java.io.Serializable & Comparable<T>> {
    public T normalize(T key) {
        return key;
    }
}
```

erasure của `T` trở thành `Serializable`. Method descriptor có thể đổi theo bound đầu tiên, dù hai interface vẫn là các ràng buộc được khai báo.

Với nhiều interface bound, thứ tự khai báo có ý nghĩa ở cấp erasure. Nếu có class bound thì class bound phải đứng trước các interface bound theo quy tắc Java.

### 6.5. Thay đổi class/interface hierarchy

Thay superclass generic, interface generic, type argument hoặc vị trí override có thể làm compiler tạo bộ bridge khác khi compile lại. Một API trước đây có bridge cho descriptor cũ có thể không còn bridge đó ở phiên bản mới.

Điều cần so sánh không chỉ là source declarations mà còn là:

- Method thực tế trong binary, gồm method synthetic/bridge.
- Descriptor của mỗi method.
- Superclass, implemented interfaces và generic supertype.
- Visibility, `static`/instance, `abstract`/concrete và `final`.
- Method được kế thừa hoặc được override.
- Mã consumer cũ sẽ sử dụng `invokevirtual`, `invokeinterface` hay dạng invocation khác.

Một thay đổi hierarchy đôi khi vẫn source-compatible khi recompile, nhưng binary cũ có thể gặp `NoSuchMethodError` hoặc `AbstractMethodError`. Kết quả phải được xác minh trên đúng tổ hợp binary.

## 7. Lỗi runtime khi bridge hoặc erased method không còn phù hợp

### 7.1. NoSuchMethodError

Thông thường xảy ra khi bytecode tham chiếu method có tên/descriptor mà runtime không còn cung cấp trong quá trình resolution.

Ví dụ, consumer cũ tham chiếu:

```text
Identity.echo(Ljava/lang/Object;)Ljava/lang/Object;
```

nhưng version mới chỉ còn:

```text
Identity.echo(Ljava/lang/Number;)Ljava/lang/Number;
```

Khi lời gọi được resolution, JVM có thể ném `NoSuchMethodError`. Thay đổi return descriptor cũng đáng lưu ý vì JVM descriptor gồm cả return type.

### 7.2. AbstractMethodError

Có thể xảy ra khi interface/class method được resolution nhưng receiver thực tế không có implementation concrete phù hợp với method được yêu cầu.

Ví dụ, một thư viện thay đổi generic interface làm erased method descriptor khác, trong khi implementation được build từ version cũ chưa được compile lại. Tùy hierarchy và call site, lời gọi interface có thể dẫn tới `AbstractMethodError`.

Cần kiểm tra interface v1/v2, implementation class v1/v2 và bridge method mà compiler tạo. Đừng sửa lỗi bằng cách thêm cast trong consumer trước khi hiểu method runtime đang thiếu.

### 7.3. ClassCastException

Bridge thường chứa cast để chuyển erased parameter về kiểu cụ thể của implementation. Client raw type hoặc unchecked cast không đúng có thể đẩy giá trị sai kiểu qua bridge và làm lỗi runtime.

Đối với return type generic, compiler consumer cũng có thể chèn `checkcast` tại nơi sử dụng giá trị trả về. Nếu thư viện thay đổi kiểu phần tử nhưng giữ descriptor, cast trong consumer cũ có thể thất bại.

### 7.4. IncompatibleClassChangeError và các linkage error khác

Một thay đổi class thành interface, instance method thành static method, thay đổi access hoặc hierarchy có thể dẫn tới các lỗi linkage khác. `NoSuchMethodError` và `AbstractMethodError` là những trường hợp con của nhóm lỗi liên kết; không nên quy tất cả về type erasure.

Trước khi kết luận nguyên nhân, đọc stack trace, kiểm tra jar thực sự được nạp và đối chiếu class-file API của các phiên bản tham gia.

## 8. Generic overload và name clash do erasure

Java không cho phép hai method trong cùng class chỉ khác type argument sau erasure:

```java
class Processor {
    void process(List<String> values) {
    }

    // Không hợp lệ: cùng erasure với method trên.
    void process(List<Integer> values) {
    }
}
```

Cả hai erasure thành `process(List)`. Compiler báo name clash vì JVM không thể phân biệt hai overload chỉ dựa vào type argument đã bị xóa.

Tương tự, khi mở rộng generic superclass, một subclass có thể vô tình khai báo method có cùng erasure với inherited method nhưng không override hợp lệ theo quy tắc source. Đây là lý do compiler có lỗi dạng “name clash: same erasure, yet neither overrides the other”.

Ví dụ minh họa rủi ro:

```java
class Parent<T> {
    void consume(T value) {
    }
}

// Khi xem source cần đối chiếu erasure và quy tắc override của method mới.
class Child extends Parent<String> {
    // Một method cùng tên nhận Object có thể đụng erasure
    // của method kế thừa và dẫn tới lỗi name clash.
    void consume(Object value) {
    }
}
```

Mục tiêu không phải tạo thêm overload bằng mọi giá. Cần xác định liệu thay đổi nên là override đúng kiểu, method có tên khác, interface riêng hoặc adapter.

### 8.1. Generics và overload resolution là hai lớp khác nhau

Type erasure diễn ra khi compiler tạo bytecode. Trước đó, overload resolution của source vẫn sử dụng type argument, upper bound, wildcard, inference và các quy tắc Java. Thêm hoặc sửa generic overload có thể làm lời gọi cũ trở nên ambiguous hoặc chọn method khác khi compile lại.

Chẳng hạn, API có:

```java
void handle(Object value) {
}

void handle(Number value) {
}
```

và client có biến kiểu `Integer` thì `handle(Number)` là overload cụ thể hơn. Nhưng nếu method generic mới có ràng buộc phức tạp, compiler cần suy luận type parameter trước khi chọn overload. Không thể nhìn hai erased descriptor rồi suy ra source compiler sẽ chọn gì.

Khi đánh giá generic API change, kiểm tra cả:

- Method invocation với đối số `null`.
- Type inference từ assignment/return context.
- Wildcard như `? extends Number` và `? super Integer`.
- Raw type và unchecked conversion.
- Lambda và method reference với target functional interface.
- Generic varargs, boxing và primitive widening.
- Erasure name clash và bridge method được sinh.

## 9. Raw types, heap pollution và binary compatibility

Raw type cho phép tương tác với code trước generics hoặc code đã loại bỏ type argument. Ví dụ:

```java
List<String> names = new ArrayList<>();
List raw = names;

raw.add(123); // unchecked warning

String first = names.get(0); // có thể ClassCastException
```

Runtime collection vẫn là một `ArrayList` và phần lớn type argument `String` không được reify. Compiler đã hứa `names.get(0)` là `String`, nên có thể chèn cast ở consumer. Giá trị `Integer` do raw access đưa vào làm cast thất bại.

Trong migration, code cũ thường chứa raw type, unchecked cast hoặc generic varargs. Khi thư viện thay đổi generic contract, những điểm này có nguy cơ phát sinh lỗi runtime dù API ở cấp descriptor không đổi.

Một số dấu hiệu cần rà soát:

- Compiler warning `rawtypes` và `unchecked`.
- Cast từ raw collection sang collection có type argument.
- Generic varargs và các trường hợp heap pollution.
- Reflection tạo `List`/`Map` rồi ép sang kiểu generic.
- Dữ liệu từ JSON, database hoặc message queue được ánh xạ vào generic type.
- Generated source dùng raw type để tương tác với framework hoặc thư viện cũ.

Không coi việc thêm `@SuppressWarnings` là biện pháp bảo đảm compatibility. Nếu cần chấp nhận unchecked operation, phải ghi rõ giả định về dữ liệu và có test xác nhận.

## 10. Reflection và framework nhìn generics khác JVM linkage

JVM dùng erased descriptor để liên kết method, nhưng reflection có thể đọc generic `Signature` metadata:

```java
Method method = Repository.class.getMethod("findAll");

System.out.println(method.getReturnType());
System.out.println(method.getGenericReturnType());
```

Với return type `List<Customer>`, `getReturnType()` thường trả về `List.class`; `getGenericReturnType()` có thể trả về `ParameterizedType` chứa `Customer`.

Các framework như JSON serializer/deserializer, dependency injection, ORM, HTTP client, type token library và validation framework có thể dùng generic metadata để suy luận model, converter hoặc binding.

Do đó, thay đổi `List<Customer>` thành `List<Order>` có thể giữ descriptor nhưng khiến framework chọn kiểu deserialize khác. Đó là behavioral compatibility risk dù JVM không báo `NoSuchMethodError`.

### 10.1. Bridge method trong reflection

Một class có bridge có thể xuất hiện nhiều method cùng tên trong kết quả `getDeclaredMethods()`. Nếu framework tự duyệt method mà không phân biệt bridge và method gốc, nó có thể:

- Đăng ký cùng một handler hai lần.
- Chọn nhầm method cho serializer hoặc mapper.
- Đếm nhầm số method trong API.
- Không xử lý đúng annotation hoặc generic metadata.
- Áp dụng validation, security hoặc transaction advice không như mong đợi.

Các framework hiện đại thường có chiến lược nhận diện bridge, nhưng khi nâng JDK/framework hoặc thay đổi annotation processor, cần kiểm tra đúng version và hành vi thực tế.

### 10.2. Generic metadata có thể bị công cụ build làm mất

Bytecode optimizer, obfuscator, shading, minimizer hoặc công cụ biến đổi class có thể can thiệp vào `Signature` attribute hoặc synthetic/bridge methods. Nếu metadata generic bị loại bỏ, JVM có thể vẫn nạp class nhưng framework dựa vào reflection sẽ thiếu thông tin kiểu cần thiết.

Trong build phát hành, so sánh artifact sau toàn bộ bước packaging với class file vừa compile. Không chỉ kiểm tra thư mục `build/classes` nếu production thực sự chạy shaded JAR hoặc container image chứa artifact đã qua biến đổi.

## 11. Generics trong API công bố cho consumer khác module

Khi một module Java công bố thư viện dùng chung, generic API có thể trở thành hợp đồng với nhiều consumer được compile ở thời điểm khác nhau.

Có ba nhóm consumer cần xác định:

1. **Consumer đã biên dịch:** chỉ có class/JAR cũ, cần tiếp tục liên kết với thư viện mới.
2. **Consumer có source và sẽ compile lại:** chịu ảnh hưởng type checking, inference và overload resolution của API mới.
3. **Consumer dùng reflection/code generation:** có thể phụ thuộc generic `Signature`, annotation, bridge và tên method khi chạy.

Nếu chỉ test unit trong repository thư viện, nhóm thường chưa kiểm chứng được consumer đã biên dịch từ version trước. Điều đó đặc biệt nguy hiểm với plugin API, SDK public, framework extension point và thư viện dùng chung cho nhiều dịch vụ.

Khi nâng framework hoặc JDK, cần ghi rõ version của cả provider và consumer. Một module có thể được biên dịch trên JDK 21 nhưng target Java 17; module khác vẫn chạy JDK 17; thêm một dependency bắc cầu có thể đã được compile với erased descriptor khác.

## 12. Quy trình phân tích một thay đổi generic API

### Bước 1: Chốt hai artifact cần so sánh

Xác định library v1 và v2 bằng group/artifact/version, commit và checksum. Kiểm tra artifact đúng đang nằm trên compile/runtime classpath. Nếu nhiều version cùng có mặt, trước tiên phải xác định version được class loader chọn.

### Bước 2: Ghi source declaration trước và sau

Lưu khai báo class/interface, type parameter, upper bound, method generic, return type, parameter type, superclass và implemented interface.

Ví dụ bảng ghi nhận:

| Thành phần | v1 | v2 |
|---|---|---|
| Type parameter | `T` | `T extends Number` |
| Method | `T echo(T)` | `T echo(T)` |
| Erasure của T | `Object` | `Number` |
| Descriptor | `(Object)Object` | `(Number)Number` |
| Rủi ro | Baseline | Có thể phá binary compatibility |

### Bước 3: So sánh JVM descriptor

Dùng `javap -s` hoặc công cụ API diff trên cả hai artifact:

```bash
javap -classpath lib-v1.jar -p -s com.example.Identity
javap -classpath lib-v2.jar -p -s com.example.Identity
```

Không chỉ nhìn `T echo(T)` trong source; hãy xác định erased parameter và return descriptor của method.

### Bước 4: So sánh bridge và synthetic methods

Quan sát class file bằng:

```bash
javap -classpath lib-v1.jar -p -v com.example.MyNode
javap -classpath lib-v2.jar -p -v com.example.MyNode
```

Tìm `ACC_BRIDGE`, `ACC_SYNTHETIC` và các descriptor cũ/mới. Nếu thay đổi hierarchy hoặc method return type, đặc biệt chú ý bridge được thêm, bớt hoặc có body khác.

### Bước 5: Compile source consumer cũ với v2

Giữ source của consumer v1, thay dependency sang v2 và compile lại. Ghi:

- Lỗi generic type inference.
- Incompatible type hoặc method không tìm thấy.
- Name clash.
- Ambiguous overload.
- Unchecked warning mới.
- Thay đổi method được compiler chọn.

Kết quả này đánh giá source compatibility, không thay thế test binary.

### Bước 6: Chạy binary consumer cũ với v2

Dùng class file consumer đã compile với v1, thay v1 bằng v2 trên runtime classpath mà không compile lại consumer, rồi chạy luồng liên quan.

Đây là kiểm tra binary compatibility. Nếu bị lỗi, xác định tên class, method descriptor, method owner và class loader thực tế trong stack trace.

### Bước 7: Chạy behavioral và integration tests

Kiểm tra dữ liệu thực qua cast, generic collection, serializer, dependency injection, reflection, plugin loading và bridge dispatch. Source/binary pass chưa chứng minh serialization, validation hoặc transaction semantics giữ nguyên.

### Bước 8: Lưu kết quả vào compatibility matrix

Mỗi vấn đề cần có component, version, affected method, source/binary/runtime impact, bằng chứng, owner, hướng xử lý và điều kiện đóng.

## 13. Công cụ hỗ trợ phân tích

### 13.1. javap

`javap` là công cụ trực tiếp nhất để quan sát các yếu tố liên quan erasure/bridge:

```bash
javap -classpath library.jar -p -s com.example.Api
javap -classpath library.jar -p -c -v com.example.Api
```

Tập trung vào descriptor, `Signature`, `ACC_BRIDGE`, `ACC_SYNTHETIC`, inheritance và instruction invocation.

### 13.2. japicmp và Revapi

Các công cụ so sánh API như japicmp hoặc Revapi có thể phát hiện method bị xóa, thay đổi return/parameter type, hierarchy, visibility và các khác biệt binary/source. Cần cấu hình đúng artifact baseline, version plugin và phạm vi public API.

Một số thay đổi generic `Signature` có thể được coi là source compatibility change dù descriptor không đổi. Hãy đọc loại cảnh báo mà công cụ phát ra, không gom mọi thay đổi thành “breaking” hoặc “non-breaking” duy nhất.

### 13.3. Dependency graph

Gradle và Maven có thể chọn version dependency khác với version được khai báo trực tiếp. Lệnh tham khảo:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency example-library --configuration runtimeClasspath
./mvnw dependency:tree
```

Đối chiếu graph giữa compile và runtime, kể cả dependency bắc cầu. `NoSuchMethodError` có thể do consumer compile với một version nhưng runtime nạp version khác, không phải do mã generic mới bị lỗi.

### 13.4. jdeps

`jdeps` giúp phân tích phụ thuộc class, package và module; nó không phải công cụ kiểm tra toàn bộ generic `Signature`, bridge dispatch hay source compatibility. Có thể dùng để hỗ trợ hiểu phụ thuộc, nhưng cần `javap`, API diff và consumer test để đánh giá tình huống erasure/bridge.

## 14. Cấu hình build và JDK khi kiểm chứng

Cần ghi riêng JDK chạy build, JDK dùng để compile và JVM chạy consumer. Ví dụ, khi build bằng JDK 21 nhưng vẫn phát hành thư viện hỗ trợ Java 17, `--release 17` giới hạn API Java nền tảng và bytecode mà compiler sinh ra. Nó không tự đảm bảo dependency bên thứ ba giữ binary API tương thích.

Ví dụ Gradle Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Ví dụ Maven Compiler Plugin:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Ngay cả với cấu hình đúng, vẫn cần đối chiếu library binary và bridge method. `--release` không ngăn nhà cung cấp dependency xóa erased method hoặc đổi generic bound.

Trong multi-module build, kiểm tra cả generated source, annotation processor, Kotlin/Groovy/Scala compilation và custom source set. Mỗi compiler có cấu hình riêng; không giả định `options.release` của `JavaCompile` áp dụng cho mọi task.

## 15. Chiến lược thiết kế API giữ tương thích

### 15.1. Tránh đổi bound của type parameter trong API đã phát hành

Thay `T` thành `T extends Number` có thể đổi erased descriptor. Nếu cần giới hạn dữ liệu, có thể bổ sung method mới với tên rõ ràng, value object hoặc adapter, đồng thời giữ method cũ trong giai đoạn chuyển tiếp.

### 15.2. Không coi type argument là chi tiết nội bộ nếu API public có generic Signature

Đổi `List<String>` thành `List<Integer>` giữ descriptor nhưng có thể phá source consumer và runtime behavior. Nếu contract dữ liệu thay đổi, cần migration guide, compatibility test và đôi khi nên tạo method/DTO mới.

### 15.3. Không phụ thuộc vào bridge do tình cờ sinh ra

Bridge method là cơ chế compiler hỗ trợ overriding theo chuẩn Java. Không nên thiết kế API bằng cách gọi trực tiếp bridge qua reflection hay phụ thuộc vào tên/flags không được công bố làm hợp đồng. Nếu một bridge đã là phần cần thiết cho binary cũ, phải giữ ABI tương thích qua quá trình migration.

### 15.4. Dùng adapter khi cần phá vỡ generic contract

Nếu v2 bắt buộc thay đổi từ kiểu `Object` sang `Number`, giữ một method với descriptor cũ và chuyển tiếp dữ liệu một cách có kiểm soát là một chiến lược. Tuy nhiên, cần thiết kế sao cho khai báo source không va chạm erasure hoặc tạo name clash. Nhiều trường hợp phải dùng tên method khác, wrapper type hoặc một compatibility class riêng.

Không nên tự thêm một method `echo(Object)` bên cạnh `echo(T extends Number)` mà không xem erasure, override và overload; cách làm này có thể tạo overload mới với semantics khác hoặc xung đột khai báo trong hierarchy.

### 15.5. Dùng major version cho breaking change có chủ đích

Nếu không thể duy trì descriptor, source contract hoặc behavior cũ, hãy công bố breaking change, xác định version chuyển tiếp và hướng dẫn consumer compile lại. Với API dùng ngoài tổ chức, cần thông báo cả các thay đổi không gây lỗi compile nhưng thay đổi dữ liệu trả về.

## 16. Ví dụ xuyên suốt: đổi generic bound trong thư viện dùng chung

Giả sử v1 của thư viện `core-api` có:

```java
package com.example.core;

public class ValueHolder<T> {
    private T value;

    public ValueHolder(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Consumer v1:

```java
ValueHolder<Integer> holder = new ValueHolder<>(10);
holder.set(20);
Integer current = holder.get();
```

Ở v1, constructor, `get` và `set` dùng erasure `Object`. Sau đó v2 đổi class thành:

```java
package com.example.core;

public class ValueHolder<T extends Number> {
    private T value;

    public ValueHolder(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
```

Các descriptor liên quan đổi:

| Thành phần | v1 | v2 |
|---|---|---|
| Constructor | `(Ljava/lang/Object;)V` | `(Ljava/lang/Number;)V` |
| `get` | `()Ljava/lang/Object;` | `()Ljava/lang/Number;` |
| `set` | `(Ljava/lang/Object;)V` | `(Ljava/lang/Number;)V` |

Consumer cũ vẫn chứa symbolic reference tới constructor và method của v1. Chạy binary đó với v2 có thể dẫn tới `NoSuchMethodError` khi resolution tới descriptor cũ.

Mặt khác, source consumer dùng `ValueHolder<Integer>` có thể compile thành công với v2 nếu compile lại. Điều này cho thấy:

- Source tương tự có thể vẫn compile.
- Binary cũ có thể không còn liên kết.
- Không thể suy ra binary compatibility từ việc source consumer mới compile được.

Một phương án migration có kiểm soát là giữ class/API v1 trong một giai đoạn và bổ sung API mới, chẳng hạn `NumericValueHolder<T extends Number>`. Consumer mới dùng API mới; consumer cũ vẫn có class và descriptor trước đây. Nhóm có thể loại bỏ API cũ trong major version sau khi có kế hoạch nâng cấp.

## 17. Những sai lầm thường gặp

| Nhận định sai | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| “Generics bị xóa nên đổi khai báo generic luôn binary-safe” | Bound đầu tiên có thể làm đổi erasure và descriptor | So sánh erased method/constructor descriptors |
| “`List<String>` và `List<Integer>` là hai runtime type khác nhau” | Cả hai thường có cùng erasure `List` | Tách source type contract khỏi runtime descriptor |
| “Bridge method chỉ là metadata, có thể xóa” | Bytecode consumer có thể cần bridge để dispatch đúng | Kiểm tra `ACC_BRIDGE` và giữ ABI phù hợp |
| “Thay bound chỉ ảnh hưởng compiler warning” | Có thể gây `NoSuchMethodError` | Chạy binary cũ với thư viện mới |
| “Compile lại toàn bộ và pass là đủ” | Không kiểm tra consumer binary đã phát hành | Tách source và binary compatibility tests |
| “Giữ descriptor thì hành vi chắc chắn giữ nguyên” | Cast, generic metadata và serializer có thể thay đổi | Kiểm tra behavior/reflection/serialization |
| “Bridge nào cũng do generic sinh ra” | Covariant return có thể cần bridge | Đọc bytecode và hierarchy thực tế |
| “Chỉ test class chính, bỏ qua shaded JAR” | Packaging có thể thay đổi metadata hoặc bridge | Kiểm tra artifact cuối sau transformation |
| “`--release 17` bảo đảm mọi dependency chạy trên Java 17” | Nó chỉ kiểm soát source/platform API trong compilation của compiler đó | Kiểm tra dependency graph và runtime target |
| “Dùng raw type để sửa lỗi generic” | Bỏ type checking và chuyển lỗi sang runtime cast | Giữ kiểu tường minh, dùng adapter có kiểm chứng |

## 18. Hồ sơ bàn giao cho một thay đổi generic API

Với một library/framework update có thay đổi type parameter, bound hoặc method override, hồ sơ tối thiểu nên có:

1. **Baseline:** artifact v1/v2, version, commit, checksum và JDK/build tool.
2. **Generic API diff:** thay đổi type parameter, bound, wildcard, method generic, return/parameter type.
3. **Erasure diff:** method/constructor descriptor trước và sau.
4. **Bridge inventory:** các method `ACC_BRIDGE`/`ACC_SYNTHETIC` được thêm, bớt hoặc thay đổi.
5. **Hierarchy diff:** superclass, interface, override và implementation quan trọng.
6. **Consumer source report:** compile source cũ với API mới.
7. **Consumer binary report:** chạy binary cũ với API mới mà không compile lại.
8. **Behavior report:** raw type, cast, reflection, serializer, DI, plugin và generated code.
9. **Dependency evidence:** version được compile và version được nạp ở runtime.
10. **Migration decision:** phương án giữ ABI, adapter, deprecation hoặc major breaking release.

### Checklist trước khi phát hành

- [ ] Đã xác định type parameter nào thay đổi và erasure tương ứng.
- [ ] Đã kiểm tra bound đầu tiên, kể cả multiple bounds.
- [ ] Đã so sánh JVM descriptor của method và constructor.
- [ ] Đã kiểm tra generic `Signature` metadata và các consumer dùng reflection.
- [ ] Đã kiểm tra bridge/synthetic methods sau khi compile và packaging.
- [ ] Đã rà soát overriding, covariant return và generic interface hierarchy.
- [ ] Đã kiểm tra name clash và overload resolution khi compile consumer.
- [ ] Đã đánh giá raw type, unchecked cast và heap pollution.
- [ ] Đã phân biệt source, binary và behavioral compatibility.
- [ ] Đã compile source consumer cũ với thư viện mới.
- [ ] Đã chạy binary consumer cũ với thư viện mới.
- [ ] Đã chạy artifact trên runtime tối thiểu được hỗ trợ.
- [ ] Đã xác minh dependency graph và artifact được nạp thực tế.
- [ ] Đã chuẩn bị migration note và phương án giữ tương thích nếu cần.

**Type erasure** quyết định các kiểu mà JVM thật sự thấy; **bridge method** giúp giữ đúng override/dispatch khi source generics hoặc covariant return tạo ra descriptor khác nhau. Khi sửa API dùng generics, nhóm cần đánh giá cả descriptor, bridge, generic metadata và hành vi runtime. Một thay đổi chỉ ở type argument có thể giữ binary linkage nhưng phá source/behavior, còn thay đổi bound hoặc hierarchy có thể làm binary cũ không còn liên kết. Các phép kiểm tra source, binary và runtime độc lập là cơ sở để phát hành Java migration có bằng chứng.
