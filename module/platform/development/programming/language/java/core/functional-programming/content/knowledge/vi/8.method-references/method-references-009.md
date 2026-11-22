# Thời điểm đánh giá đối tượng nhận lời gọi và nguy cơ null trong method reference

## Mục tiêu

Trong Java, biểu thức **method reference** `receiver::instanceMethod` có thể trông giống lambda `() -> receiver.instanceMethod()`, nhưng hai cách viết **không hoàn toàn tương đương về thời điểm thực thi**. Đối tượng đứng trước dấu `::` được đánh giá khi method reference được tạo, và bound method reference cần receiver khác `null` ngay ở thời điểm đó. Với lambda, việc đánh giá receiver nằm trong thân lambda có thể chỉ diễn ra lúc functional method được gọi.

Sau bài học, bạn có thể:

- Phân biệt **bound instance method reference** (`object::method`), **unbound instance method reference** (`Type::method`), static method reference và lambda.
- Xác định lúc nào biểu thức receiver có tác dụng phụ được đánh giá và lúc nào method thực sự được gọi.
- Giải thích vì sao `nullable::method` có thể ném `NullPointerException` **ngay khi tạo**, còn `() -> nullable.method()` thường ném **khi gọi lambda**.
- Biết receiver được **gắn vào object nào**, hiểu rằng object vẫn có thể thay đổi trạng thái sau khi reference được tạo.
- Chọn cách viết phù hợp khi đăng ký callback, trì hoãn tạo đối tượng, làm việc với `Optional` và xây API chấp nhận functional interface.
- Chạy ví dụ Java 17 và dự đoán chính xác thứ tự stdout cũng như vị trí phát sinh lỗi.

## 1. Method reference không phải là lời gọi phương thức ngay lập tức

Method reference là một biểu thức dùng cú pháp `::` để cung cấp implementation cho một **functional interface**. Nó cần **target type** có phương thức trừu tượng duy nhất (*SAM*).

Ví dụ:

```java
String name = "Java";
java.util.function.Supplier<Integer> length = name::length;
```

`Supplier<Integer>` có descriptor `() -> Integer`. Cụm `name::length` tạo một hành vi để khi gọi `length.get()` sẽ gọi `length()` trên chuỗi đã được gắn vào method reference. Việc tạo reference **không đồng nghĩa** với việc gọi `name.length()`.

```java
int value = length.get(); // 4
```

Vì `String.length()` trả `int`, kết quả được boxing sang `Integer` theo target type. Nếu không dùng target type như `Supplier<Integer>`, Java thường không thể suy luận ý định chỉ từ `name::length`; `var x = name::length` không hợp lệ vì thiếu kiểu đích là functional interface.

Tuy nhiên có **hai thời điểm khác nhau** cần phân biệt:

1. **Thời điểm tạo method reference:** đánh giá phần receiver bên trái `::` (nếu là biểu thức receiver của bound reference), kiểm tra receiver không `null` và liên kết tới đối tượng.
2. **Thời điểm gọi functional method:** thực thi phương thức được tham chiếu trên receiver đã gắn.

Ở phần lớn tình huống, sai sót bắt nguồn từ việc chỉ nghĩ tới thời điểm thứ hai và bỏ qua việc đánh giá receiver ở thời điểm thứ nhất.

## 2. Bốn dạng tham chiếu phương thức và receiver

| Dạng | Ví dụ | Receiver được lấy ở đâu? | Rủi ro `null` liên quan |
| --- | --- | --- | --- |
| **Bound instance**: `expression::instanceMethod` | `profile::greet` | Biểu thức `profile` được đánh giá khi tạo reference và instance được gắn vào reference | Receiver `null` gây NPE ngay khi tạo |
| **Unbound instance**: `Type::instanceMethod` | `Profile::greet` | Receiver là đối số của functional method khi được gọi | Đối số receiver `null` gây NPE khi gọi |
| **Static**: `Type::staticMethod` | `Integer::parseInt` | Không có receiver đối tượng cho lời gọi static | Không có phép kiểm tra receiver như bound instance; tham số `null` vẫn có thể gây lỗi bên trong static method |
| **Constructor**: `Type::new` | `StringBuilder::new` | Tạo object khi functional method được gọi | Không có receiver object trước khi tạo; constructor vẫn có thể ném ngoại lệ |

Dạng bound:

```java
Profile profile = new Profile("Lan");
java.util.function.Supplier<String> bound = profile::greet;
System.out.println(bound.get()); // Hello Lan
```

Dạng unbound:

```java
java.util.function.Function<Profile, String> unbound =
        Profile::greet;
System.out.println(unbound.apply(profile)); // Hello Lan
```

Hai đoạn này **minh họa trong ngữ cảnh** lớp `Profile` đã định nghĩa ở chương trình đầy đủ phía dưới. Chúng khác nhau về descriptor:

- `profile::greet` khớp `() -> String` vì receiver đã được gắn.
- `Profile::greet` khớp `(Profile) -> String` vì receiver phải được **truyền ở tham số đầu tiên** của lần gọi.

Không suy luận rằng có dấu `::` thì lúc nào cũng có bound receiver. Chỉ những method reference dạng **biểu thức instance có receiver được đánh giá** mới phát sinh kiểm tra `null` sớm như trường hợp `profile::greet`.

## 3. Thứ tự thời điểm đánh giá receiver

### 3.1. Biểu thức trước dấu :: được đánh giá ngay

```java
java.util.function.Supplier<String> greeting =
        loadProfile()::greet;
```

Nếu `loadProfile()` có tác dụng phụ (ghi log, tăng bộ đếm, truy vấn database), tác dụng phụ xảy ra **khi xây dựng `greeting`**, chứ không chờ tới `greeting.get()`. Nếu `loadProfile()` trả `null`, việc tạo bound reference ném `NullPointerException` ngay tại biểu thức tạo reference. Phương thức `greet()` chưa được gọi.

Có thể hình dung thứ tự logic như sau:

```text
1. Đánh giá loadProfile()
2. Kiểm tra kết quả có null không
3. Gắn receiver hợp lệ vào method reference
4. [Sau này] Ai đó gọi greeting.get()
5. Thực thi greet() trên receiver đã gắn
```

Đây là sơ đồ ngữ nghĩa, **không phải mã Java hay mô tả một cơ chế JVM bắt buộc**. Compiler/JVM có thể sử dụng nhiều cách triển khai lambda và method reference; chương trình chỉ nên dựa trên ngữ nghĩa đã được ngôn ngữ bảo đảm.

### 3.2. Lambda có thể trì hoãn toàn bộ việc lấy receiver

```java
java.util.function.Supplier<String> greeting =
        () -> loadProfile().greet();
```

Ở đây body `loadProfile().greet()` chỉ chạy khi có lời gọi `greeting.get()`. Nếu không ai gọi `get()`, `loadProfile()` không được thực thi vì thân lambda không chạy. Nếu gọi `get()` nhiều lần, `loadProfile()` cũng có thể được gọi nhiều lần, tạo ra các receiver khác nhau.

Đối chiếu:

| Thao tác | `loadProfile()::greet` | `() -> loadProfile().greet()` |
| --- | --- | --- |
| Khi tạo đối tượng hàm | Gọi `loadProfile()` một lần và kiểm tra null | Chưa gọi `loadProfile()` |
| Khi gọi functional method lần thứ nhất | Gọi `greet()` trên instance đã gắn | Gọi `loadProfile()` rồi `greet()` |
| Khi gọi functional method lần tiếp theo | Vẫn gọi `greet()` trên instance đã gắn trước đó | Tiếp tục gọi `loadProfile()` rồi `greet()` |
| Khi factory trả `null` | NPE khi tạo reference | NPE khi thực thi body |
| Khi factory có I/O | I/O xảy ra lúc tạo reference | I/O xảy ra mỗi lần thực thi body, nếu đến được bước đó |

Nếu mục tiêu là **hoãn cả việc lấy hoặc tạo receiver** thì lambda là lựa chọn tự nhiên. Nếu muốn **chọn receiver một lần và dùng lại** thì bound reference diễn đạt đúng ý. Nhưng cả hai đều có thể có side effect/ngoại lệ; quyết định phải dựa trên hợp đồng gọi.

### 3.3. Receiver được gắn một lần, không phải đóng băng trạng thái

```java
StringBuilder builder = new StringBuilder("A");
java.util.function.Supplier<String> text = builder::toString;

builder.append("B");
System.out.println(text.get()); // AB
```

Ở lúc tạo `text`, instance `builder` đã được gắn. Lúc gọi `text.get()`, phương thức `toString()` được chạy trên **chính instance đó**, khi nội dung đã trở thành `"AB"`. Method reference không phải snapshot của kết quả phương thức. Nó gắn object, không tự cache kết quả gọi method.

Việc receiver không đổi về **danh tính** không có nghĩa trạng thái của nó bất biến. Cần phân biệt **bound receiver** với **memoization** hoặc **eager method invocation**.

## 4. Chương trình Java 17 hoàn chỉnh

Chương trình kiểm tra đủ bốn trường hợp quan trọng: bound receiver hợp lệ; receiver được tạo qua phương thức có tác dụng phụ; receiver null ở bound reference so với lambda; và unbound reference với receiver được truyền sau.

Lưu nội dung sau vào tệp **`MethodReferenceReceiverDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.function.Supplier;

public class MethodReferenceReceiverDemo {
    record Profile(String name) {
        String greet() {
            return "Hello " + name;
        }
    }

    static Profile load(AtomicInteger calls) {
        System.out.println("load #" + calls.incrementAndGet());
        return new Profile("An");
    }

    public static void main(String[] args) {
        Profile profile = new Profile("Lan");
        Supplier<String> bound = profile::greet;
        Supplier<String> lambda = () -> profile.greet();

        System.out.println("created");
        System.out.println("bound: " + bound.get());
        System.out.println("lambda: " + lambda.get());

        AtomicInteger calls = new AtomicInteger();
        Supplier<String> fromCall = load(calls)::greet;
        System.out.println("after reference: " + calls.get());

        Supplier<String> delayed = () -> load(calls).greet();
        System.out.println("after lambda: " + calls.get());

        System.out.println("fromCall: " + fromCall.get());
        System.out.println("delayed: " + delayed.get());

        Profile absent = null;

        try {
            Supplier<String> rejected = absent::greet;
            System.out.println(rejected.get());
        } catch (NullPointerException e) {
            System.out.println("bound null: NPE at creation");
        }

        Supplier<String> later = () -> absent.greet();
        System.out.println("lambda with null created");
        try {
            later.get();
        } catch (NullPointerException e) {
            System.out.println("lambda null: NPE at get");
        }

        Function<Profile, String> unbound = Profile::greet;
        System.out.println("unbound: " + unbound.apply(profile));
        try {
            unbound.apply(null);
        } catch (NullPointerException e) {
            System.out.println("unbound null: NPE at apply");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac MethodReferenceReceiverDemo.java
java MethodReferenceReceiverDemo
```

**Stdout chính xác:**

```text
created
bound: Hello Lan
lambda: Hello Lan
load #1
after reference: 1
after lambda: 1
fromCall: Hello An
load #2
delayed: Hello An
bound null: NPE at creation
lambda with null created
lambda null: NPE at get
unbound: Hello Lan
unbound null: NPE at apply
```

**Giải thích thứ tự đầu ra:**

1. `profile::greet` và `() -> profile.greet()` được tạo, nhưng chưa gọi `greet()`. Vì vậy dòng đầu tiên là `created`.
2. `bound.get()` và `lambda.get()` cùng gọi `greet()` trên `profile` và trả `Hello Lan`. Với lambda này, `profile` đã được capture dưới dạng tham chiếu cục bộ *effectively final*.
3. Khi tạo `fromCall = load(calls)::greet`, `load(calls)` lập tức chạy, in `load #1` và tạo instance `Profile("An")`. Do đó `after reference: 1`.
4. Khi tạo `delayed = () -> load(calls).greet()`, `load` chưa chạy; `after lambda: 1` chứng minh điều này.
5. `fromCall.get()` chỉ gọi `greet()` trên instance đã gắn và không tăng `calls`; trả `Hello An`.
6. `delayed.get()` gọi `load(calls)`, in `load #2` trước khi câu lệnh `System.out.println("delayed: " + ...)` in `delayed: Hello An`. Đây là thứ tự đánh giá biểu thức của Java.
7. `absent::greet` ném `NullPointerException` ngay khi tạo, vì receiver bằng `null`; control chuyển vào `catch`, nên lệnh in trong khối `try` không chạy.
8. Lambda `() -> absent.greet()` vẫn tạo được dù `absent` là `null`. NPE xuất hiện khi `later.get()` thực thi body.
9. `Profile::greet` không gắn instance tại thời điểm tạo. `unbound.apply(profile)` thành công, còn `unbound.apply(null)` ném NPE lúc gọi vì receiver được truyền vào là `null`.

Các ngoại lệ trong ví dụ đều được bắt rõ, giúp chương trình in kết quả xác định và tiếp tục chạy đến cuối.

## 5. Vì sao nullable::method và () -> nullable.method() khác nhau?

Giả sử có biến:

```java
Profile nullable = null;
```

Đoạn sau **ném NPE ngay khi biểu thức method reference được đánh giá**:

```java
Supplier<String> a = nullable::greet;
```

Kể cả chưa gọi `a.get()`, bound reference vẫn không thể được tạo thành công với receiver `null`.

Trong khi đó:

```java
Supplier<String> b = () -> nullable.greet();
// Phép gán ở trên thành công.
// Lệnh dưới mới ném NPE:
b.get();
```

Cả hai cùng có thể gây NPE, nhưng **thời điểm** khác nhau. Điều này ảnh hưởng đến:

- **Luồng điều khiển:** lỗi ném trong constructor, khởi tạo field hoặc đăng ký callback thay vì khi callback chạy.
- **Try/catch:** muốn bắt NPE do bound receiver null thì khối `try` phải bao quanh **việc tạo reference**; muốn bắt NPE từ lambda thì khối `try` phải bao quanh **việc gọi**.
- **Logging và stack trace:** vị trí lỗi được quan sát khác nhau, có thể khiến chẩn đoán khó hiểu nếu người đọc giả định cả hai giống nhau.
- **Lazy initialization:** bound reference có thể buộc truy cập dữ liệu ngay, phá ý định trì hoãn.
- **Chính sách kiểm tra đầu vào:** nhận diện `null` sớm đôi khi tốt, nhưng cũng có trường hợp muốn điều kiện hóa việc thực thi để không bao giờ dereference.

Ví dụ với method registration:

```java
// Minh họa; Action là một class có phương thức void runAction().
Action action = null;

Runnable callback = action::runAction; // NPE tại bước đăng ký
```

Viết thành lambda:

```java
Runnable callback = () -> action.runAction();
// Chỉ khi callback.run() mới thử dereference action.
```

Đây là **hai đoạn minh họa riêng**, không gộp vào cùng scope vì trùng tên biến. Nếu callback không bao giờ được gọi, lambda không phát sinh NPE từ body; bound reference đã thất bại ngay tại lúc đăng ký. Không dùng thay đổi thời điểm ném lỗi để che giấu việc dữ liệu đáng lẽ phải có.

## 6. Đánh giá receiver có tác dụng phụ hoặc có thể ném lỗi

Phần trước dấu `::` có thể là một lời gọi phương thức, phép truy cập field hoặc biểu thức phức tạp. Nó không nhất thiết chỉ là tên biến.

```java
Supplier<String> first = repository.loadCurrent()::name;
```

Đây là đoạn minh họa: `repository.loadCurrent()` trả về một object có phương thức `name()` không tham số. Nếu `loadCurrent()` gọi database, database bị truy cập **ngay khi tạo `first`**. Nếu trả `null`, NPE phát sinh ngay. Nếu chính `loadCurrent()` ném ngoại lệ, ngoại lệ ấy xảy ra trong quá trình đánh giá receiver, trước lúc tạo thành công method reference.

Tương đương theo ý tưởng “lấy receiver một lần”:

```java
// Cũng là minh họa, chỉ sử dụng khi kiểu Repo và Data đã định nghĩa.
Data current = repository.loadCurrent();
Supplier<String> first = current::name;
```

Ở dạng tường minh, bước đọc repository dễ nhận thấy hơn. Cần lưu ý: nếu `current` bằng `null`, dòng tạo method reference vẫn ném NPE. Nếu dùng `Objects.requireNonNull(current, "current")`, chương trình kiểm tra non-null rõ ràng trước khi tạo callback.

Nếu nghiệp vụ thực sự yêu cầu lấy dữ liệu mới ở **mỗi lần gọi**, dùng lambda:

```java
Supplier<String> fresh = () -> repository.loadCurrent().name();
```

Trong trường hợp này, thao tác repository được trì hoãn và chạy lại mỗi lần `fresh.get()`. Nếu có I/O hoặc lỗi, caller phải biết hợp đồng này. Lưu ý: `Supplier.get()` không khai báo checked exception, nên nếu `loadCurrent()` ném một checked exception (ví dụ `IOException`), lambda phải xử lý hoặc chuyển theo chính sách, hoặc dùng functional interface riêng khai báo `throws`. Không thể mặc định mọi thao tác I/O đặt trong Supplier đều biên dịch.

### Đánh giá receiver một lần không tương đương cache kết quả

```java
Supplier<String> bound = load(calls)::greet;
```

Trong ví dụ hoàn chỉnh, `load(calls)` chạy một lần, nhưng **`greet()` vẫn chạy mỗi khi `bound.get()` được gọi**. Nếu receiver là object mutable và `greet()` đọc field mutable, kết quả có thể khác nhau sau mỗi lần gọi. Chỉ có **receiver** được gắn sớm; kết quả phương thức không được tự động memoize.

Ngược lại:

```java
String saved = load(calls).greet();
Supplier<String> cachedValue = () -> saved;
```

Ở đây cả `load` và `greet` chạy **ngay trước khi tạo Supplier**, còn các lần `cachedValue.get()` trả lại giá trị `saved`. Cách viết này mới thể hiện việc tính kết quả một lần rồi giữ lại, khác với method reference.

## 7. Unbound instance method reference: null đến từ đối số lúc gọi

Một method reference dạng `Profile::greet` không cần một `Profile` cụ thể khi tạo:

```java
Function<Profile, String> f = Profile::greet;
```

Với target `Function<Profile,String>`, khi gọi `f.apply(profile)`, tham số đầu tiên `profile` đóng vai trò receiver của `greet()`. Nếu đưa `null` vào `f.apply(null)`, phép gọi có thể ném NPE tại thời điểm thực thi; bản thân biểu thức `Profile::greet` đã được tạo từ trước mà không cần kiểm tra receiver cụ thể.

Viết tương đương về ý định:

```java
Function<Profile, String> f = person -> person.greet();
```

Đây cũng là hàm nhận một `Profile`. Trường hợp `person == null` thì lỗi xảy ra khi body thực thi. Hai dòng trên là **hai phương án khai báo riêng**, không đặt cùng lúc trong một scope với cùng tên `f`.

Khi muốn dùng một method cho nhiều đối tượng khác nhau, unbound reference thường phù hợp:

```java
// Đây là đoạn minh họa dùng Profile ở chương trình chính.
java.util.List<Profile> profiles =
        java.util.List.of(new Profile("Lan"), new Profile("An"));

java.util.List<String> greetings = profiles.stream()
        .map(Profile::greet)
        .toList(); // [Hello Lan, Hello An]
```

`Stream.map` nhận một mapper được gọi với từng phần tử tại thời điểm stream chạy. Với phần tử không phải `null`, method reference hoạt động bình thường. `List.of` không cho tạo danh sách chứa `null`; với một Stream từ nguồn có thể chứa `null`, `Profile::greet` sẽ không tự lọc bỏ phần tử null.

Nếu null được phép trong đầu vào và muốn bỏ qua, có thể:

```java
java.util.List<String> safeNames = profiles.stream()
        .filter(java.util.Objects::nonNull)
        .map(Profile::greet)
        .toList();
```

Cấu trúc này lọc phần tử null trước khi gọi `greet`. Nhưng phải quyết định về mặt nghiệp vụ: null là dữ liệu cần bỏ qua, cần thay thế hay là lỗi dữ liệu cần báo ngay?

## 8. Dùng Optional và kiểm tra null đúng ranh giới

Không thể dùng `Optional` để “cứu” một bound method reference sau khi nó đã được đánh giá với receiver null:

```java
// Nếu profile null, dòng dưới thất bại trước khi có Supplier hợp lệ.
Supplier<String> greet = profile::greet;
```

Nếu một receiver có thể vắng mặt, hãy lựa chọn ngữ nghĩa rõ ràng.

**Trường hợp 1 — thiếu receiver là lỗi:** kiểm tra sớm và đưa ra thông báo:

```java
Profile checked = java.util.Objects.requireNonNull(
        profile, "profile is required");
Supplier<String> greet = checked::greet;
```

NPE vẫn phát sinh khi profile thiếu, nhưng vị trí và thông báo lỗi giúp thể hiện hợp đồng. Đây là hai câu lệnh minh họa cần nằm trong một scope đã khai báo `profile`.

**Trường hợp 2 — thiếu receiver cho giá trị dự phòng:**

```java
String greeting = java.util.Optional.ofNullable(profile)
        .map(Profile::greet)
        .orElse("Hello Guest");
```

Khi `profile` không có, mapper sẽ không chạy và kết quả là `Hello Guest`. `Optional.map` nhận `Function<Profile,String>` nên `Profile::greet` là **unbound reference** phù hợp, không gắn receiver null vào lúc tạo.

**Trường hợp 3 — chỉ gọi callback khi có receiver:**

```java
java.util.Optional.ofNullable(profile).ifPresent(
        p -> System.out.println(p.greet())
);
```

Lambda chỉ được thực thi khi `Optional` có giá trị. Lưu ý `Optional.ofNullable(profile)` lấy giá trị `profile` tại **thời điểm gọi `ofNullable`**; không tự theo dõi việc một field có thể đổi trong tương lai.

Đừng bao bọc một lỗi null bất ngờ bằng `Optional` nếu điều đó âm thầm bỏ qua một bất biến bắt buộc. Chọn giữa fail-fast, giá trị mặc định và bỏ qua theo yêu cầu nghiệp vụ.

## 9. Lambda capture, identity và việc thay đổi receiver

Một biến local được capture bởi lambda phải là `final` hoặc *effectively final*:

```java
Profile profile = new Profile("Lan");
Supplier<String> later = () -> profile.greet();
```

Đoạn này hợp lệ nếu `profile` không bị gán lại sau khi khởi tạo. Nếu code gán `profile = new Profile("An")` sau đó trong cùng phương thức, compiler sẽ không cho lambda capture biến này.

Nếu đối tượng **mutable** được capture, nội dung của nó vẫn có thể đổi:

```java
StringBuilder builder = new StringBuilder("A");
Supplier<String> byReference = builder::toString;
Supplier<String> byLambda = () -> builder.toString();

builder.append("B");
System.out.println(byReference.get()); // AB
System.out.println(byLambda.get());    // AB
```

Cả hai đang dùng cùng instance `builder`. Với các tham chiếu đến cùng object ổn định như vậy, hành vi có thể giống nhau. **Khác biệt nổi bật** xuất hiện khi biểu thức receiver cần được đánh giá, receiver có thể null, hoặc việc lấy object có side effect. Không phải cứ gặp `::` thì hành vi mới hoặc an toàn hơn lambda.

Nếu receiver là một field có thể được gán lại, sự khác biệt càng rõ:

```java
// Minh họa ngữ nghĩa khi field holder.current có thể đổi:
Supplier<String> fixed = holder.current::greet;
Supplier<String> dynamic = () -> holder.current.greet();
```

`fixed` giữ instance của `holder.current` tại thời điểm tạo. `dynamic` đọc `holder.current` mỗi lần body thực thi và có thể thấy instance khác hoặc `null`. Đây chỉ là đoạn minh họa với `holder` do ứng dụng định nghĩa; không phải chương trình độc lập. Dùng đồng bộ hoặc thiết kế trạng thái phù hợp nếu field có thể thay đổi từ luồng khác; method reference/lambda không tự cung cấp tính an toàn luồng.

## 10. Ứng dụng thực tế: callback, listener và lazy computation

Một API thường nhận `Runnable`, `Supplier<T>`, `Consumer<T>` hoặc `Function<T,R>`. Hành vi về receiver phải được hiểu **trước khi đăng ký**:

```java
// Minh họa: notifier có phương thức void notifyUser().
Runnable readyCallback = notifier::notifyUser;
Runnable deferredCallback = () -> notifier.notifyUser();
```

Với một biến notifier không null, hai callback có thể tương đương về kết quả khi chạy. Nhưng nếu notifier null ngay tại đăng ký, bản bound thất bại tức thì, còn lambda chỉ thất bại nếu được gọi. Nếu notifier là mutable field và thay đổi sau khi đăng ký, cách gắn receiver có thể làm thay đổi đối tượng thực thi callback.

Khi gọi đăng ký:

```java
// Minh họa, callbackRegistry nhận Runnable:
callbackRegistry.register(notifier::notifyUser);
```

Lập luận đúng là biểu thức đối số `notifier::notifyUser` phải tạo xong trước khi method `register` được gọi. Nếu notifier null, NPE xảy ra trước khi đăng ký thành công. Đặt trong `try/catch` bao quanh riêng `register(...)` vẫn có thể bắt lỗi nếu toàn bộ lời gọi nằm trong try, nhưng không nên cho rằng lỗi xuất hiện khi registry *chạy* callback.

Khi receiver cần tạo đắt đỏ hoặc chỉ cần dùng nếu callback thực sự chạy, viết:

```java
callbackRegistry.register(() -> createNotifier().notifyUser());
```

`createNotifier()` được trì hoãn. Tuy nhiên, nếu callback được gọi nhiều lần, factory cũng có thể chạy nhiều lần; hãy xác định mục tiêu là “tạo mỗi lần”, “tạo một lần khi đăng ký”, hay “tạo một lần ở lần gọi đầu rồi cache”. Lambda không tự cung cấp cơ chế cache lazy an toàn giữa nhiều thread.

## 11. Lỗi và hiểu lầm thường gặp

1. **Tưởng `receiver::method` thực thi method ngay.** Sai: nó đánh giá và gắn receiver ngay, còn thực thi method khi gọi functional method.
2. **Tưởng `receiver::method` giống hoàn toàn `() -> receiver.method()`.** Sai nếu receiver là biểu thức có side effect, nullable hoặc thay đổi ở những thời điểm khác nhau.
3. **Tưởng null chỉ gây lỗi khi gọi `get()`.** Sai với bound reference: kiểm tra receiver non-null xảy ra lúc tạo reference.
4. **Tưởng `Type::instanceMethod` kiểm tra một receiver lúc khai báo.** Dạng unbound chưa có receiver cụ thể; null được kiểm tra khi nhận đối số và thực thi lời gọi.
5. **Tưởng bound reference giữ kết quả method.** Nó gắn **đối tượng**, không tự cache return value; method có thể đọc trạng thái mới.
6. **Tưởng lambda trì hoãn mọi thứ xung quanh nó.** Chỉ những biểu thức nằm **trong body** mới trì hoãn; nếu bạn tính receiver hoặc giá trị trước khi tạo lambda, việc tính đó vẫn là eager.
7. **Bỏ qua side effect của factory:** `find()::process` có thể truy vấn hoặc gây lỗi ngay; `() -> find().process()` đổi thời điểm và số lần truy vấn.
8. **Dùng `Optional` chỉ để che giấu lỗi dữ liệu bắt buộc:** cần phân biệt nullable hợp lệ với bất biến nghiệp vụ bị vi phạm.
9. **Giả định reference và lambda tự an toàn khi concurrency:** chúng không tự bảo vệ mutable receiver hoặc I/O; cần hợp đồng đồng bộ và vòng đời phù hợp.
10. **Dựa vào identity của lambda object:** không nên mặc định mỗi lần đánh giá một lambda/method reference sẽ cấp một object mới hay cùng object; Java có quyền lựa chọn chiến lược triển khai.

## 12. Bài tự kiểm tra

1. Với `String text = null; Supplier<Integer> s = text::length;`, lỗi xảy ra trước hay sau khi gọi `s.get()`?
2. Với `String text = null; Supplier<Integer> s = () -> text.length();`, khi nào NPE xuất hiện?
3. Giả sử `getService()` tăng bộ đếm và trả về service hợp lệ. Phân biệt số lần gọi `getService()` khi tạo rồi gọi hai lần `getService()::execute` so với `() -> getService().execute()`.
4. Với `Function<String,Integer> f = String::length;`, khi nào `null` trở thành receiver, và vì sao biểu thức method reference vẫn tạo được?
5. Một `StringBuilder` được dùng trong `builder::toString`. Nếu thêm ký tự sau khi tạo reference nhưng trước khi gọi, kết quả phản ánh nội dung cũ hay mới?
6. Giả sử `repository.load()` có thể trả null. Hãy chọn cách xử lý phù hợp cho (a) thiếu là lỗi; (b) thiếu thì trả giá trị mặc định; (c) chỉ truy vấn khi callback được gọi.
7. So sánh `Service service = factory(); Supplier<String> s = service::status;` với `Supplier<String> s = () -> factory().status();` về thời điểm thực thi factory và khả năng đổi service.
8. Khi nhận `Stream<Profile>` có thể chứa null, vì sao `.map(Profile::greet)` có thể gặp NPE? Sửa theo chính sách loại bỏ null.

**Gợi ý đáp án:**

- (1) NPE xảy ra lúc tạo bound reference `text::length`, trước khi `s` được gán thành công.
- (2) Tạo lambda thành công; NPE xảy ra lúc `s.get()`.
- (3) Bound gọi factory một lần khi tạo; lambda gọi factory mỗi lần body chạy (trong giả thiết hai lần gọi).
- (4) `String::length` unbound, nhận receiver ở `f.apply(...)`; `f.apply(null)` gây NPE khi gọi.
- (5) Nội dung mới, vì `toString()` chỉ chạy khi functional method được gọi.
- (6) Fail-fast bằng kiểm tra non-null; `Optional.ofNullable(...).map(...).orElse(...)` hoặc xử lý tương đương; đưa factory vào body lambda để trì hoãn.
- (7) Bản đầu lấy service một lần và gắn receiver; bản thứ hai lấy service lại khi mỗi lần `get()` chạy.
- (8) Dạng unbound nhận phần tử làm receiver; dùng `filter(Objects::nonNull)` trước `map` nếu nghiệp vụ cho phép bỏ null.

## Kết luận

Điểm quan trọng nhất của `receiver::method` là **đánh giá receiver và kiểm tra non-null khi tạo bound method reference, nhưng chỉ gọi method khi functional method được thực thi**. Lambda `() -> receiver.method()` có thể trì hoãn việc đánh giá receiver và do đó làm đổi thời điểm tác dụng phụ hoặc ngoại lệ. Dạng `Type::instanceMethod` lại nhận receiver như đối số lúc gọi.

Hiểu đúng ba tình huống này giúp đọc chính xác luồng thực thi, quyết định lúc nào nên fail-fast, lúc nào nên trì hoãn công việc và tránh lỗi null khó phát hiện khi đăng ký callback hay xử lý dữ liệu bằng functional API.
