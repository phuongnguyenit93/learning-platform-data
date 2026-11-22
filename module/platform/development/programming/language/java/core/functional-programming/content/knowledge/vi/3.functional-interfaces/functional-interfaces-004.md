# Phương thức tương ứng với phương thức `public` của `Object` trong functional interface

## 1. Vấn đề: đếm phương thức trừu tượng như thế nào?

Một **functional interface** (giao diện hàm) có một **phương thức chức năng duy nhất** (*single abstract method*, SAM): đó là hợp đồng mà biểu thức lambda hoặc tham chiếu phương thức phải thực hiện. Quy tắc này không đơn giản là “đếm tất cả dòng khai báo `abstract` trong giao diện”.

Theo Java Language Specification (JLS) §9.8, khi xác định SAM, các phương thức trừu tượng có chữ ký tương ứng với **phương thức thực thể `public` của `java.lang.Object`** được bỏ khỏi tập phương thức dùng để xác định giao diện hàm. Vì vậy một interface có thể khai báo `equals(Object)`, `hashCode()`, `toString()` và vẫn là functional interface nếu ngoài các phương thức đó chỉ còn một phương thức trừu tượng nghiệp vụ.

Quy tắc này giúp phân biệt **hợp đồng vốn có của mọi đối tượng Java** với **hành vi mới** mà lambda phải cung cấp. Nó cũng giải thích vì sao `java.util.Comparator<T>` vẫn có thể được tạo bằng lambda dù giao diện đó khai báo `equals(Object)` bên cạnh `compare(T, T)`.

Mục tiêu bài học: đọc đúng các khai báo dễ gây nhầm, nhận biết ngoại lệ của `Object`, kiểm tra `@FunctionalInterface` và viết lambda chạy được.

## 2. Những phương thức nào được loại khỏi phép đếm SAM?

Trong ba phương thức quen thuộc, chữ ký và kiểu trả về hợp lệ khi khai báo lại trong interface như sau:

| Khai báo trừu tượng trong interface | Phương thức `public` tương ứng của `Object` | Có được tính là SAM mới? |
| --- | --- | --- |
| `boolean equals(Object other);` | `Object.equals(Object)` | Không |
| `int hashCode();` | `Object.hashCode()` | Không |
| `String toString();` | `Object.toString()` | Không |
| `boolean equals(String text);` | **Không trùng** `equals(Object)`: khác loại tham số | Có |
| `Object clone();` | `Object.clone()` là `protected`, không phải `public` | Có |
| `void run();` | Không có phương thức tương ứng trong `Object` | Có |

**Điều kiện nằm ở chữ ký, không chỉ ở tên.** `equals(Object)` được loại; `equals(String)` là một nạp chồng (*overload*) khác, vì vậy vẫn được tính là một phương thức trừu tượng riêng. Tên `toString` trùng nhưng khai báo sai kiểu trả về cũng không hợp lệ: nó không trở thành phương thức SAM mới.

Phạm vi quy tắc là các phương thức **`public` và không phải `static` của `Object`**. `clone()` và `finalize()` của `Object` có phạm vi `protected`, nên nếu một interface tự khai báo các phương thức cùng chữ ký theo dạng `public abstract`, chúng **không được miễn đếm**. Các phương thức `final` như `getClass()`, `wait()`, `notify()` vốn không thể được khai báo lại theo cách ghi đè hợp lệ trong interface; không được suy ra rằng có thể tự do thêm những khai báo này để tạo giao diện hàm.

Việc “không tính vào SAM” chỉ có nghĩa là lambda **không phải cung cấp phần thân riêng cho chúng**. Đối tượng thực thi giao diện vẫn có các hành vi `Object` thông thường. Bản thân `Object.equals` còn có quy ước tính phản xạ, đối xứng, bắc cầu và tính nhất quán; quy tắc SAM không thay đổi các hợp đồng đó.

## 3. Ví dụ đầy đủ: nhiều khai báo nhưng vẫn chỉ một SAM

Tạo tệp `ObjectMethodSamDemo.java` với toàn bộ nội dung sau:

```java
import java.util.Comparator;

@FunctionalInterface
interface Job {
    boolean equals(Object other);
    int hashCode();
    String toString();
    void run(String text);
}

interface IdentityRule {
    boolean equals(Object other);
}

@FunctionalInterface
interface Normalizer extends IdentityRule {
    String normalize(String text);
}

public class ObjectMethodSamDemo {
    public static void main(String[] args) {
        Job job = text -> System.out.println("Xu ly: " + text);
        job.run("Java");
        System.out.println(job.equals(job));

        Normalizer normalizer = String::trim;
        System.out.println("[" + normalizer.normalize("  functional  ") + "]");

        Comparator<String> byLength =
                (a, b) -> Integer.compare(a.length(), b.length());
        System.out.println(byLength.compare("Go", "Java"));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 ObjectMethodSamDemo.java
java ObjectMethodSamDemo
```

Kết quả:

```text
Xu ly: Java
true
[functional]
-1
```

Giải thích:

1. `Job` khai báo bốn phương thức trừu tượng, nhưng ba phương thức `equals(Object)`, `hashCode()`, `toString()` tương ứng với phương thức `public` của `Object`, nên **chỉ `run(String)` là SAM**. Biểu thức `text -> ...` cung cấp cách thực hiện `run`.
2. `job.run("Java")` thực thi phần thân lambda. `job.equals(job)` gọi phương thức so sánh đối tượng, không gọi `run`. Kết quả `true` vì đối tượng được so với chính nó.
3. `IdentityRule` chỉ khai báo `equals(Object)`, vì thế tự nó **không phải** functional interface (không có SAM mới). `Normalizer` kế thừa giao diện này và thêm đúng `normalize(String)`; do đó `Normalizer` **là** functional interface. `String::trim` là tham chiếu phương thức phù hợp với `normalize`.
4. `Comparator<String>` là ví dụ thật của Java: `compare(T, T)` là phương thức chức năng, còn khai báo `equals(Object)` không làm tăng số SAM. Lambda so sánh độ dài của `"Go"` (2) và `"Java"` (4) trả `-1`.

Các kết quả và tính hợp lệ của chương trình đã được kiểm chứng bằng `javac --release 17` và `java`. Giao diện phụ nằm cùng tệp và không khai báo `public` để tên tệp khớp với lớp `public ObjectMethodSamDemo`.

## 4. Vì sao `equals`, `hashCode`, `toString` được đối xử đặc biệt?

Mọi đối tượng của lớp Java đều kế thừa từ `Object` (trực tiếp hoặc gián tiếp). Một lớp triển khai interface đã có các phương thức `public` thích hợp từ `Object`, hoặc có thể ghi đè chúng theo hợp đồng của lớp. Vì thế, việc interface nhắc lại phương thức `equals(Object)` không tạo ra hành vi nghiệp vụ độc lập mà lambda cần định nghĩa.

Hãy so sánh:

```java
@FunctionalInterface
interface TextOperation {
    String transform(String text);   // Phương thức chức năng duy nhất

    boolean equals(Object other);   // Không tính vào SAM
    int hashCode();                 // Không tính vào SAM
    String toString();              // Không tính vào SAM
}
```

Ví dụ khai báo trên hợp lệ. Lambda như `TextOperation upper = String::toUpperCase;` thực hiện `transform`. Nó không định nghĩa cách `equals`, `hashCode` hay `toString` hoạt động; cách các phương thức `Object` hoạt động đối với đối tượng lambda thuộc về việc triển khai đối tượng. Không nên xây logic nghiệp vụ dựa trên tên lớp sinh ra, chuỗi `toString()` hay việc hai lần đánh giá lambda có cùng đối tượng hay không.

**Phân biệt “phương thức đã được lớp cung cấp” với “phương thức trừu tượng cần lambda thực hiện”:** ngoại lệ này thuộc phép xác định SAM theo ngôn ngữ Java, không phải cơ chế xóa các phương thức `Object` khỏi đối tượng lúc chạy.

## 5. Hai kiểu dễ nhầm nhất

### 5.1. Interface chỉ khai báo `equals(Object)`

```text
@FunctionalInterface
interface OnlyEquality {
    boolean equals(Object other);
}
```

Đoạn này **cố ý không hợp lệ với `@FunctionalInterface`**. `equals(Object)` được loại khỏi tập đếm, nên interface không còn phương thức trừu tượng nào làm SAM. Nếu bỏ annotation, bản thân khai báo interface vẫn hợp lệ; tuy nhiên không thể dùng lambda để tạo một `OnlyEquality`. Trình biên dịch phát hiện lỗi ở annotation thay vì chờ đến lúc dùng lambda.

### 5.2. Interface có `equals(String)` và `run()`

```text
@FunctionalInterface
interface TwoAbstractMethods {
    void run();
    boolean equals(String text);
}
```

Đoạn này cũng **cố ý không hợp lệ**: `equals(String)` là phương thức khác `Object.equals(Object)` và được tính vào tập phương thức trừu tượng. Khi có cả `run()`, giao diện có **hai** hành vi trừu tượng không tương đương, nên không còn là functional interface.

Quy tắc ghi nhớ: **trùng tên không đồng nghĩa trùng chữ ký**. Phải xét tên, kiểu tham số và các quan hệ ghi đè hợp lệ. Chỉ `equals(Object)` đúng chữ ký mới thuộc ngoại lệ trong trường hợp đang xét.

## 6. Phân biệt với `default`, `static` và `private`

Ngoài ngoại lệ của `Object`, một interface có thể có phương thức `default`, `static` hoặc `private` cùng với SAM. Các phương thức này có thân triển khai hoặc vai trò riêng, nên không tạo ra một phương thức trừu tượng nghiệp vụ thứ hai.

```java
@FunctionalInterface
interface LabeledAction {
    void execute(); // SAM duy nhất

    boolean equals(Object other); // Khai báo lại phương thức Object

    default String label() {
        return "action";
    }

    static LabeledAction of(Runnable runnable) {
        return runnable::run;
    }

    private String prefix() {
        return "label";
    }

    default String decoratedLabel() {
        return prefix() + ":" + label();
    }
}
```

Đây là một khai báo interface hợp lệ trong Java 17+, dùng làm ví dụ bên trong một tệp nguồn (không phải chương trình có `main`). Phương thức `execute` vẫn là SAM; `label`, `decoratedLabel`, `of` và `prefix` không được tính là phương thức trừu tượng.

**Lưu ý quan trọng:** không được cung cấp phần thân `default` để ghi đè trực tiếp phương thức `public` của `Object` trong interface. Chẳng hạn:

```text
interface InvalidDefault {
    default String toString() {
        return "x";
    }
}
```

Đây là **ví dụ cố ý không biên dịch**, vì `default toString()` ghi đè phương thức của `Object`. Muốn thay đổi `toString`, lớp triển khai giao diện phải tự ghi đè theo quy tắc của lớp; không thể dùng phương thức `default` như trên.

## 7. `clone()` là ngoại lệ của… ngoại lệ

`Object.clone()` có phạm vi `protected`, khác với `equals`, `hashCode` và `toString`. Vì thế, nếu một interface khai báo `Object clone();`, phương thức đó **được tính** vào tập phương thức trừu tượng khi xét SAM.

Xem hai trường hợp:

```text
@FunctionalInterface
interface CloneOnly {
    Object clone();
}
// Hợp lệ: clone() là một SAM mới vì Object.clone() không public.

@FunctionalInterface
interface CloneAndRun {
    Object clone();
    void run();
}
// Không hợp lệ: có hai phương thức trừu tượng cần triển khai.
```

Phần mã được trình bày để phân loại hợp lệ/không hợp lệ; không phải một chương trình có thể biên dịch nguyên khối vì `CloneAndRun` cố ý sai. Cả hai kết luận đã được kiểm chứng với `javac --release 17`.

Nên tránh dùng `clone` làm API học tập thông thường nếu không thật sự cần hành vi sao chép: nó có những yêu cầu và hạn chế riêng liên quan đến `Cloneable`, quyền truy cập và kiểu trả về. Điểm cần nắm ở đây là **`protected` không được miễn đếm**, dù phương thức có sẵn trong `Object`.

## 8. Cách tự xác định một interface có phải functional interface hay không

1. Tập hợp các phương thức **trừu tượng** được khai báo trực tiếp hoặc kế thừa từ các interface cha. Phương thức `default`, `static` và `private` không phải các yêu cầu trừu tượng cần lambda thực hiện.
2. Loại các phương thức trừu tượng có chữ ký tương ứng với **phương thức thực thể `public` của `Object`**, trong những ví dụ thông dụng là `equals(Object)`, `hashCode()`, `toString()`.
3. Với các phương thức trừu tượng còn lại, kiểm tra các chữ ký có thể **ghi đè tương đương** (*override-equivalent*) để đại diện cho một hợp đồng duy nhất, đồng thời các kiểu trả về phải tương thích theo quy tắc *return-type-substitutable*. Không được chỉ đếm số dòng khi interface có kế thừa.
4. Nếu xác định được đúng một hợp đồng chức năng, interface có thể làm kiểu đích của lambda/tham chiếu phương thức. Nếu không có hợp đồng nào, hoặc có nhiều hợp đồng độc lập, interface không phải functional interface.
5. Thêm `@FunctionalInterface` để trình biên dịch kiểm tra ý định thiết kế. Annotation này **không biến** một interface nhiều SAM thành hợp lệ, và một interface đủ điều kiện vẫn là functional interface kể cả khi thiếu annotation.

Trường hợp kế thừa với hai phương thức trừu tượng có chữ ký tương đương có thể vẫn là một hợp đồng chức năng nếu điều kiện tương thích kiểu trả về thỏa mãn. Không nên khái quát rằng “mọi interface có hơn một khai báo `abstract` đều sai”: ngoại lệ `Object` là một lý do, và các phương thức trừu tượng có thể ghi đè tương đương là lý do khác.

## 9. Ví dụ thực tế: `Comparator<T>`

`java.util.Comparator<T>` là functional interface phổ biến. Hợp đồng nghiệp vụ của nó là so sánh hai giá trị qua `int compare(T a, T b)`. Giao diện cũng khai báo `boolean equals(Object obj)` nhưng khai báo đó không làm tăng số SAM.

```java
Comparator<String> comparator =
        (left, right) -> Integer.compare(left.length(), right.length());
```

Đây là đoạn minh họa đặt trong một phương thức, sau khi `import java.util.Comparator;`; cùng phép so sánh này đã xuất hiện trong chương trình chạy đầy đủ ở mục 3. Lý do lambda hợp lệ không phải vì Java “bỏ qua mọi phương thức khác `compare`”, mà vì `equals(Object)` thuộc **ngoại lệ được định nghĩa rõ** trong JLS.

Khi dùng `Comparator` trong `sort`, `TreeSet`, `TreeMap`, cần nhớ các điều kiện về tính nhất quán của phép so sánh. Sự tồn tại của ngoại lệ `Object` trong phép đếm SAM không quyết định logic sắp xếp hay cách các bộ sưu tập sử dụng kết quả `compare`.

## 10. Lỗi thường gặp và cách sửa

| Nhận định hoặc đoạn mã sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Khai báo `equals(Object)` làm interface có hai SAM.” | `equals(Object)` tương ứng với phương thức `public` của `Object`. | Loại nó khỏi phép đếm SAM. |
| “Chỉ có `equals(Object)` cũng đủ tạo một functional interface.” | Không còn phương thức nghiệp vụ nào sau khi loại ngoại lệ. | Interface có 0 SAM không dùng làm kiểu đích của lambda. |
| “`equals(String)` cũng được loại vì cùng tên.” | Kiểu tham số khác nên đây là phương thức nạp chồng riêng. | `equals(String)` vẫn được tính. |
| “Bất kỳ phương thức nào của `Object` đều không tính.” | `clone()` là `protected`. | Ngoại lệ chỉ dành cho phương thức thực thể `public`. |
| “Có thể viết `default toString()` trong interface.” | Java cấm phương thức `default` ghi đè phương thức `Object`. | Chỉ khai báo trừu tượng tương ứng, hoặc cho lớp triển khai ghi đè. |
| “Gắn `@FunctionalInterface` là đủ.” | Annotation chỉ kiểm tra ràng buộc, không nới lỏng ràng buộc. | Xác định đúng SAM trước khi gắn annotation. |
| “Phải cài đặt cả `equals` và `run` trong lambda.” | Lambda chỉ mô tả đúng một phương thức chức năng. | Lambda cung cấp phần thân cho `run`; các phương thức `Object` có cơ chế đối tượng riêng. |

## 11. Tự kiểm tra

**Bài 1.** Interface dưới đây có phải functional interface không? Vì sao?

```java
interface A {
    String toString();
    int hashCode();
    int compute(int x);
}
```

Đáp án: **Có**. Hai phương thức đầu tương ứng `public` của `Object`, chỉ `compute(int)` là SAM.

**Bài 2.** Phân loại giao diện:

```java
interface B {
    boolean equals(String text);
    int hashCode();
}
```

Đáp án: **Có**. `hashCode()` bị loại; `equals(String)` khác `equals(Object)` nên là một SAM hợp lệ. Nếu thêm `void run();`, giao diện sẽ có hai phương thức trừu tượng độc lập và không còn là functional interface.

**Bài 3.** Nếu một interface cha chỉ khai báo `boolean equals(Object)`, interface con thêm `void execute()` có thể nhận lambda không?

Đáp án: **Có**. Phương thức kế thừa `equals(Object)` không tính là SAM; `execute()` là phương thức chức năng duy nhất của interface con, giống mô hình `IdentityRule` → `Normalizer` ở ví dụ mục 3.

**Bài 4.** Phân biệt hai dòng:

```text
boolean equals(Object other);  // Không tính vào SAM
boolean equals(String other);  // Có tính vào SAM
```

Đáp án: loại tham số quyết định hai chữ ký khác nhau. Không được rút gọn quy tắc thành “cứ có tên `equals` thì không tính”.

## 12. Ghi nhớ và tài liệu chuẩn

- Ngoại lệ áp dụng khi đếm phương thức trừu tượng của **functional interface**: không tính những phương thức tương ứng với **phương thức thực thể `public` của `Object`**.
- `equals(Object)`, `hashCode()`, `toString()` là ba trường hợp thực tế quan trọng; `equals(String)` và `clone()` **không** thuộc ngoại lệ trên.
- Functional interface cần **một hợp đồng chức năng duy nhất** sau khi áp dụng quy tắc ngoại lệ và quy tắc ghi đè tương đương. Lambda chỉ triển khai hợp đồng đó.
- `@FunctionalInterface` giúp phát hiện sai sót ngay tại khai báo. `Comparator<T>` là ví dụ có sẵn cho việc khai báo `equals(Object)` mà vẫn dùng được lambda.

Nguồn quy tắc: [Java Language Specification — §9.8 Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8), kết hợp với quy định thành viên và phương thức của giao diện tại JLS §9.2 và §9.4.