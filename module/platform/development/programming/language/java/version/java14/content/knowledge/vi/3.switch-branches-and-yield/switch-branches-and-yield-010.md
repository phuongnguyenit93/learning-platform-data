# `yield` như một định danh bị giới hạn theo ngữ cảnh (Java 14+)

## 1. Vấn đề cần hiểu

Từ Java 14, biểu thức `switch` có thể sử dụng câu lệnh `yield biểuThức;` để tạo kết quả cho toàn bộ biểu thức `switch`. Nhưng Java cũng có mã nguồn cũ đặt tên biến, trường hoặc phương thức là `yield`. Để hai cách dùng cùng tồn tại, ngôn ngữ **không cấm tuyệt đối** chuỗi ký tự `yield` ở mọi vị trí; thay vào đó, nó chỉ dành ý nghĩa đặc biệt cho `yield` khi xuất hiện trong **câu lệnh `yield`**, và hạn chế một số vị trí đặt tên.

Đây là ý nghĩa của cụm **“định danh bị giới hạn theo ngữ cảnh”** trong Java 14:

- `yield` có thể là **tên biến cục bộ, tham số, trường (field)** và **tên được khai báo của phương thức**.
- `yield` **không** được dùng làm **tên kiểu** (chẳng hạn `class yield`) hoặc **tên tham số kiểu** (`<yield>`).
- Nếu một phương thức có tên `yield`, việc **gọi** nó phải có phần định danh phía trước, ví dụ `obj.yield(3)`, `this.yield(3)` hay `TypeName.yield(3)` với phương thức `static`. Lời gọi trần `yield(3)` không hợp lệ.
- `yield giáTrị;` là **câu lệnh** tạo ra giá trị của biểu thức `switch` bao quanh, hoàn toàn khác với việc gọi phương thức.

**Lưu ý về thuật ngữ:** Tài liệu đặc tả Java 14 gọi `yield` là *restricted identifier* (định danh bị hạn chế); các bản Java Language Specification mới hơn, ví dụ Java 25, xếp `yield` vào nhóm *contextual keyword* (từ khóa theo ngữ cảnh). Dù cách phân loại thuật ngữ khác nhau, **các hạn chế thực tế về tên kiểu và lời gọi phương thức vẫn được áp dụng**. Bài học sử dụng cú pháp chính thức từ Java 14, không dựa vào tính năng preview hoặc cách dùng đã lỗi thời.

## 2. Vì sao không thể coi `yield` như từ khóa dành riêng thông thường?

Một từ khóa dành riêng như `class` hay `return` không thể dùng để đặt tên biến, ví dụ `int return = 1;` là không hợp lệ. `yield` khác ở chỗ sau:

~~~java
// Các đoạn dưới đây hợp lệ khi đặt trong một lớp/phương thức phù hợp:
int yield = 10;        // "yield" là tên biến cục bộ.
int score = yield + 2; // "yield" được dùng như một biểu thức đọc biến.
~~~

Nhưng khi đặt trong một nhánh có khối của `switch` expression:

~~~java
int result = switch (status) {
    case 1 -> {
        int score = 20;
        yield score; // Câu lệnh: cho switch expression nhận giá trị score.
    }
    default -> 0;
};
~~~

Đoạn trên là **mã minh họa đặt trong phương thức**, giả định `status` có kiểu `int`. Trong `yield score;`, `yield` là phần mở đầu câu lệnh đặc biệt chứ không phải tên biến hoặc lời gọi hàm. Kết quả biểu thức `switch` sẽ được gán cho `result`.

Điều này cho phép Java bổ sung cú pháp mới mà vẫn duy trì tính tương thích với nhiều định danh hiện hữu. Tuy nhiên, **có thể sử dụng** một tên không có nghĩa là **nên đặt tên mới** như vậy: `yield` rất dễ gây nhầm lẫn khi đọc mã có `switch` expression.

## 3. Các vị trí được phép và bị hạn chế

| Vị trí xuất hiện | Hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `int yield = 4;` | Có | Biến cục bộ tên `yield` |
| `int process(int yield)` | Có | Tham số phương thức tên `yield` |
| `private int yield;` | Có | Trường của lớp tên `yield` |
| `int yield(int x) { ... }` | Có | Khai báo một phương thức có tên `yield` |
| `this.yield(3)` | Có | Gọi phương thức qua đối tượng `this` |
| `obj.yield(3)` | Có | Gọi phương thức qua biến đối tượng |
| `MyType.yield(3)` | Có, nếu `yield` là `static` trong `MyType` | Gọi phương thức đã định danh bằng tên lớp |
| `yield(3)` | **Không** | Không được gọi phương thức `yield` bằng tên trần |
| `class yield { }` | **Không** | `yield` không được là tên kiểu |
| `class Box<yield> { }` | **Không** | `yield` không được là tên tham số kiểu |
| `yield value;` trong nhánh phù hợp của `switch` expression | Có | Câu lệnh `yield` tạo kết quả cho `switch` |

Trong ngữ pháp Java, hai loại tên giải thích quy tắc này:

- **`TypeIdentifier`**: tên dùng khi khai báo/tham chiếu kiểu. `yield` không được sử dụng trong nhóm này.
- **`UnqualifiedMethodIdentifier`**: tên của phương thức được gọi mà không có `đốiTượng.` hoặc `TênLớp.` ở trước. `yield` cũng không được sử dụng trong nhóm này.

Đặc tả không cấm `yield` ở các ngữ cảnh định danh khác, ví dụ tên trường hoặc tên phương thức được khai báo. Đây là lý do mã cũ có phương thức `yield` vẫn có thể tồn tại, nhưng khi gọi phải viết rõ đối tượng hoặc tên lớp.

## 4. Ví dụ biên dịch, chạy được: biến, trường, phương thức và câu lệnh `yield`

Tạo tệp **`YieldIdentifierDemo.java`** với toàn bộ mã sau. Mã sử dụng cú pháp Java 14 chính thức và cũng chạy được trên JDK mới hơn.

~~~java
public final class YieldIdentifierDemo {
    private final int yield = 5;

    // Khai báo phương thức có tên yield: hợp lệ.
    int yield(int extra) {
        return this.yield + extra;
    }

    int calculate(int code) {
        // Khai báo biến cục bộ có tên yield: hợp lệ.
        int yield = 4;

        return switch (code) {
            case 1 -> {
                int doubled = yield * 2;
                yield doubled; // yield đầu tiên là câu lệnh.
            }
            case 2 -> this.yield(yield); // Gọi method có this.
            case 3 -> {
                yield yield + 1; // yield thứ hai là tên biến!
            }
            default -> -1;
        };
    }

    public static void main(String[] args) {
        YieldIdentifierDemo demo = new YieldIdentifierDemo();

        System.out.println("Field yield: " + demo.yield);
        System.out.println("Method yield: " + demo.yield(3));
        System.out.println("Yield statement: " + demo.calculate(1));
        System.out.println("Qualified call: " + demo.calculate(2));
        System.out.println("Yield yield: " + demo.calculate(3));
    }
}
~~~

Biên dịch và chạy với JDK 14 trở lên:

~~~bash
javac -encoding UTF-8 --release 14 YieldIdentifierDemo.java
java YieldIdentifierDemo
~~~

**Stdout chính xác:**

~~~text
Field yield: 5
Method yield: 8
Yield statement: 8
Qualified call: 9
Yield yield: 5
~~~

Giải thích từng chỗ xuất hiện của `yield`:

1. `private final int yield = 5;`: `yield` là **tên field**. `demo.yield` đọc giá trị `5`, không có lời gọi phương thức.
2. `int yield(int extra)`: `yield` là **tên phương thức được khai báo**. `demo.yield(3)` gọi phương thức và trả `5 + 3 = 8`.
3. `int yield = 4;`: `yield` là **tên biến cục bộ** bên trong `calculate`. Nó che khuất field cùng tên ở dạng truy cập không định danh, vì vậy muốn đọc field thì dùng `this.yield`.
4. `case 1`: phép tính `yield * 2` dùng biến cục bộ `yield = 4` và tạo `doubled = 8`. Sau đó, `yield doubled;` là **câu lệnh** kết thúc nhánh, đưa giá trị `8` ra làm kết quả `switch`.
5. `case 2`: `this.yield(yield)` là **lời gọi phương thức có đối tượng**. `this.yield` ở đây trỏ tới phương thức, còn tham số `yield` đọc giá trị biến cục bộ `4`. Phương thức trả `5 + 4 = 9`.
6. `case 3`: `yield yield + 1;` hoàn toàn hợp lệ: `yield` thứ nhất là **câu lệnh**, `yield` thứ hai là **biến cục bộ**, nên kết quả là `4 + 1 = 5`. Đây là ví dụ nhằm hiểu cách phân tích cú pháp; **không khuyến khích đặt tên biến như vậy trong mã mới** vì khó đọc.

Mẫu `yield yield + 1;` cho thấy **vị trí cú pháp** quyết định ý nghĩa của cùng chuỗi `yield`, chứ không phải cứ thấy chữ `yield` là trình biên dịch coi nó là từ khóa không thể dùng làm tên.

## 5. Hai trường hợp không biên dịch và cách sửa

### 5.1. Không khai báo kiểu có tên `yield`

~~~java
// SAI: minh họa lỗi biên dịch, không ghép vào tệp chạy ở trên.
class yield {
}
~~~

Khi biên dịch với `--release 14`, trình biên dịch từ chối tên lớp này: `yield` là **tên kiểu bị hạn chế**. Tương tự, không khai báo `interface yield` hoặc tham số kiểu `class Container<yield>`.

Sửa bằng cách đặt tên kiểu có ý nghĩa nghiệp vụ, chẳng hạn:

~~~java
class YieldResult {
    private final int value;

    YieldResult(int value) {
        this.value = value;
    }

    int value() {
        return value;
    }
}
~~~

`YieldResult` là tên kiểu hợp lệ vì không trùng hoàn toàn với định danh bị hạn chế `yield`.

### 5.2. Không gọi phương thức `yield` bằng tên trần

~~~java
// SAI: minh họa lỗi biên dịch, không ghép vào tệp chạy.
class InvalidCall {
    int yield(int number) {
        return number + 1;
    }

    int run() {
        return yield(3); // Sai: tên phương thức không có qualifier.
    }
}
~~~

Khai báo `int yield(int number)` **hợp lệ**. Lỗi nằm tại `yield(3)`: Java không cho dùng `yield` làm tên của lời gọi phương thức không định danh. Điều này đúng **ngay cả khi lời gọi nằm ngoài một `switch` expression**.

Sửa bằng cách ghi đối tượng rõ ràng:

~~~java
class ValidCall {
    int yield(int number) {
        return number + 1;
    }

    int run() {
        return this.yield(3); // Hợp lệ; trả về 4.
    }
}
~~~

Với phương thức `static` tên `yield`, dùng `ClassName.yield(...)`; với phương thức kế thừa phù hợp có thể sử dụng `super.yield(...)`. Dù Java cho phép khai báo phương thức tên `yield`, khi thiết kế API mới nên chọn tên mô tả hành động cụ thể như `calculateYield`, `nextValue` hay `produce`.

## 6. Phân biệt ba cách dùng thường bị nhầm

**Cách A — Câu lệnh `yield`:**

~~~java
int result = switch (code) {
    case 1 -> {
        int value = 10;
        yield value;
    }
    default -> 0;
};
~~~

Dùng để đưa kết quả từ **khối nhánh** về `switch` expression. `yield` không phải `return` của phương thức và không phải `break`; nó chỉ kết thúc việc đánh giá biểu thức `switch` chứa nó.

**Cách B — Biểu thức nhánh dùng `->`:**

~~~java
int result = switch (code) {
    case 1 -> 10;
    default -> 0;
};
~~~

Không cần `yield` vì ngay sau `->` là một biểu thức giá trị. `yield` chỉ cần khi dùng khối với các câu lệnh tính toán trước khi cho ra kết quả.

**Cách C — Gọi phương thức tên `yield`:**

~~~java
int value = obj.yield(10);
~~~

Đây là **method invocation**; nó chỉ hợp lệ nếu `obj` là một biến đối tượng có phương thức `yield(int)` phù hợp. Dấu `.` phía trước phân biệt nó với câu lệnh `yield ...;`. Dòng này không yêu cầu có `switch`.

Các đoạn trên là **mã minh họa**; cần định nghĩa `code`, `obj` và phương thức tương ứng khi đưa vào chương trình đầy đủ.

## 7. Ranh giới phạm vi và lỗi dễ mắc

### `yield` phải có biểu thức `switch` làm đích

Một câu lệnh `yield 10;` đặt tự do trong thân phương thức, bên ngoài `switch` expression, là lỗi biên dịch. Nó cũng không thể nhảy qua ranh giới của một phương thức hoặc lambda nằm bên trong một nhánh để đưa giá trị ra `switch` bên ngoài. Với phương thức, dùng `return`; với lambda, dùng cú pháp trả về của lambda; với `switch` expression có khối, dùng `yield` ngay trong khối phù hợp.

Nếu có nhiều `switch` expression lồng nhau, câu lệnh `yield` tác động đến **biểu thức `switch` bao quanh gần nhất** mà nó thuộc về.

### Giá trị của `yield` phải hợp kiểu và không phải `void`

~~~java
// Minh họa trong một phương thức với biến int code.
int result = switch (code) {
    case 1 -> {
        int value = 7;
        yield value; // int, tương thích với biến result.
    }
    default -> 0;
};
~~~

Nếu một nhánh của `switch` expression kết thúc bình thường mà không đưa ra kết quả, hoặc `yield` nhận biểu thức có kiểu `void`, trình biên dịch sẽ báo lỗi. Bản thân `yield` không biến mọi câu lệnh thành một giá trị.

### Không suy diễn rằng mọi chỗ chứa từ `yield` đều là cùng một cấu trúc

Ví dụ `int yield = 4;`, `this.yield(4)`, và `yield 4;` lần lượt là **khai báo biến**, **gọi phương thức**, và **câu lệnh điều khiển**. Trình biên dịch dựa vào vị trí trong ngữ pháp. Khi đọc mã, hãy xác định trước phần đứng sau `yield`: dấu `(` trong lời gọi cần đối tượng, toán tử như `+` trong biểu thức dùng biến, hay giá trị sau câu lệnh `yield`.

### Đừng đổi mã đang dùng `yield` theo phỏng đoán

Mã cũ có biến/trường/phương thức tên `yield` **không nhất thiết sai**. Nếu sửa, hãy thay đổi theo chức năng và kiểm tra các nơi tham chiếu. Quy tắc hiện hành cấm **tên kiểu** và **lời gọi phương thức không định danh**, chứ không phải cấm mọi định danh có cùng cách viết.

## 8. Tự kiểm tra kiến thức

Xác định mỗi đoạn **hợp lệ** hay **không hợp lệ** trong Java 14+, giả sử các phần cần thiết khác đã được khai báo:

1. `int yield = 9;`
2. `int yield(int x) { return x + 1; }` (khai báo phương thức trong lớp)
3. `return yield(3);` (gọi không định danh trong phương thức)
4. `return this.yield(3);` (gọi phương thức của chính đối tượng)
5. `class yield { }`
6. `case 1 -> { yield 12; }` (nhánh thuộc một `switch` expression trả số)

**Đáp án:** (1) hợp lệ, `yield` là biến; (2) hợp lệ, khai báo tên phương thức; (3) **không hợp lệ**, thiếu đối tượng/tên lớp khi gọi phương thức `yield`; (4) hợp lệ khi phương thức `yield(int)` tồn tại và có thể được gọi; (5) **không hợp lệ**, tên kiểu bị hạn chế; (6) hợp lệ khi `switch` expression có kiểu đích tương thích.

## 9. Ghi nhớ thực hành

- `yield` mang **ý nghĩa cú pháp đặc biệt** trong `yield biểuThức;` của `switch` expression, nhưng vẫn **được phép làm tên** ở một số vị trí như biến, trường, tham số và khai báo phương thức.
- Không dùng `yield` cho **tên kiểu** hay **tham số kiểu**; không gọi phương thức có tên `yield` dưới dạng `yield(...)` không định danh.
- Nếu cần gọi phương thức cũ tên `yield`, hãy viết `this.yield(...)`, `obj.yield(...)` hoặc `ClassName.yield(...)` theo đúng loại phương thức.
- Khi viết mã mới, nên đặt tên dễ đọc như `value`, `result` hoặc tên theo nghiệp vụ để tránh nhầm với câu lệnh `yield`.

**Nguồn đặc tả chính thức:**
- [Java SE 14 Language Specification — `3.8, Identifiers](https://docs.oracle.com/javase/specs/jls/se14/html/jls-3.html#jls-3.8) — thuật ngữ `restricted identifier` khi tính năng chính thức xuất hiện.
- [Java SE 25 Language Specification — `3.8–3.9, Identifiers and Keywords](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html) — quy tắc `TypeIdentifier`, `UnqualifiedMethodIdentifier` và nhóm `contextual keyword`.
- [Java SE 25 Language Specification — `14.21, The `yield` Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.21) — ý nghĩa và giới hạn đích của câu lệnh `yield`.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361) — tính năng `switch` expression chính thức trong Java 14.
