# Truyền tham trị cho kiểu nguyên thủy và tham chiếu trong phương thức Java

## 1. Quy tắc cốt lõi: Java luôn truyền tham trị

Trong Java, khi gọi một phương thức, **giá trị của từng biểu thức đối số** được dùng để khởi tạo **biến tham số riêng của phương thức**. Cơ chế này gọi là *pass-by-value* (truyền tham trị) và áp dụng **cho cả kiểu nguyên thủy lẫn kiểu tham chiếu**.

- **Kiểu nguyên thủy** (`int`, `double`, `boolean`, `char`, ...): tham số nhận bản sao của chính giá trị, chẳng hạn `10` hoặc `true`. Thay đổi tham số không thay đổi biến ở nơi gọi.
- **Kiểu tham chiếu** (`Person`, `String`, `int[]`, ...): tham số nhận bản sao **giá trị tham chiếu** tới đối tượng. Hai biến có thể cùng tham chiếu một đối tượng; thao tác sửa trạng thái đối tượng qua tham số có thể thấy được ở nơi gọi. Tuy nhiên, **gán lại tham số** không làm thay đổi biến tham chiếu của nơi gọi.

Không có cú pháp tham số `ref`, `out` hay “pass-by-reference” trong chữ ký phương thức Java. Cụm từ “truyền tham chiếu” đôi khi được dùng không chính xác để mô tả việc đối số có kiểu tham chiếu. Nói chính xác, Java **truyền bản sao của giá trị tham chiếu**, không truyền chính biến của bên gọi cho phương thức sửa lại.

## 2. Truyền kiểu nguyên thủy: thay đổi tham số chỉ có tác dụng bên trong

Ví dụ dưới đây là đoạn mã minh họa đặt trong một lớp:

```java
static void increase(int value) {
    value += 10; // Chỉ cập nhật tham số cục bộ
}

int x = 5;
increase(x);
// x vẫn bằng 5
```

Khi gọi `increase(x)`, giá trị `5` được sao chép vào tham số `value`. Câu lệnh `value += 10` biến tham số thành `15`, nhưng biến `x` của nơi gọi không thay đổi.

Kể cả khi tham số và biến bên gọi trùng tên, chúng vẫn là hai biến khác nhau thuộc phạm vi khác nhau. Giá trị được truyền vào chỉ được xác định **tại lần gọi**; thay đổi tham số sau đó không đồng bộ ngược về biến ban đầu.

Với các giá trị `byte`, `short`, `char`, `int`, `long`, `float`, `double`, `boolean`, quy tắc là như nhau (có thể có chuyển đổi kiểu thích hợp theo quy tắc gọi phương thức, ví dụ `int` sang `long`). Muốn bên gọi nhận giá trị mới, hãy **trả về rồi gán lại**:

```java
static int increased(int value) {
    return value + 10;
}

int x = 5;
x = increased(x);
// x == 15
```

Phương thức `void` không tự đưa bản cập nhật của tham số trở lại nơi gọi.

## 3. Truyền tham chiếu: đối tượng chung, biến tham số riêng

Xét một phương thức nhận đối tượng có trạng thái thay đổi được:

```java
class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

static void rename(Person person) {
    person.name = "Lan"; // Sửa đối tượng chung
}

static void replace(Person person) {
    person = new Person("Hoa"); // Gán lại biến tham số
}
```

Ở nơi gọi:

```java
Person p = new Person("Minh");
rename(p);  // p.name trở thành "Lan"
replace(p); // p vẫn trỏ đến đối tượng có name là "Lan"
```

Khi gọi `rename(p)`, giá trị tham chiếu của `p` được sao chép vào tham số `person`. Hai biến cùng chỉ tới một đối tượng, vì vậy `person.name = "Lan"` làm đổi trường `name` trên đối tượng đó.

Khi gọi `replace(p)`, gán `person = new Person("Hoa")` chỉ đổi biến `person` **bên trong phương thức** sang đối tượng mới. Biến `p` vẫn giữ tham chiếu cũ. Cũng vì thế, `person = null` không khiến biến `p` ở nơi gọi thành `null`.

Có thể hình dung:

```text
Trước khi gán lại tham số:
  p -----------+---> Person("Lan")
  person ------+

Sau person = new Person("Hoa"):
  p ----------------> Person("Lan")
  person -----------> Person("Hoa")
```

Sơ đồ chỉ mô tả quan hệ tham chiếu, không khẳng định vị trí vật lý cụ thể của biến hay đối tượng trong bộ nhớ.

## 4. Mảng làm rõ sửa object khác gán lại tham số

Mảng `int[]` là **đối tượng**, nên tham số nhận bản sao **tham chiếu mảng**, không tự nhận bản sao từng phần tử.

~~~java
static void changeFirst(int[] numbers) { numbers[0] = 99; }
static void rebind(int[] numbers) { numbers = new int[]{7, 8}; }

int[] data = {1, 2};
changeFirst(data);
rebind(data);
System.out.println(java.util.Arrays.toString(data)); // [99, 2].
~~~

`changeFirst` sửa object dùng chung; `rebind` chỉ thay biến tham số. Với mảng hai chiều, thay `matrix[1]` là sửa **phần tử của mảng ngoài**, còn gán `matrix = other` là gán lại tham số. Bài tiếp theo phân tích riêng mảng nhiều chiều, alias, `clone()` và hợp đồng sửa mảng/trả mảng.


## 5. Ví dụ Java 17+ đầy đủ, chạy và đối chiếu đầu ra

Tạo tệp **`PassByValueDemo.java`**:

```java
import java.util.Arrays;

public class PassByValueDemo {
    static class Person {
        String name;

        Person(String name) {
            this.name = name;
        }
    }

    static void changeNumber(int number) {
        number = 99;
        System.out.println("Trong changeNumber: " + number);
    }

    static void changeElement(int[] values) {
        values[0] = 99;
    }

    static void replaceArray(int[] values) {
        values = new int[]{7, 8};
        System.out.println("Trong replaceArray: " + Arrays.toString(values));
    }

    static void rename(Person person) {
        person.name = "Lan";
    }

    static void replacePerson(Person person) {
        person = new Person("Hoa");
        System.out.println("Trong replacePerson: " + person.name);
    }

    static void changeString(String text) {
        text = text.toUpperCase();
        System.out.println("Trong changeString: " + text);
    }

    static int[] doubledCopy(int[] source) {
        int[] copy = source.clone();
        for (int i = 0; i < copy.length; i++) {
            copy[i] *= 2;
        }
        return copy;
    }

    public static void main(String[] args) {
        int number = 10;
        changeNumber(number);
        System.out.println("Sau changeNumber: " + number);

        int[] values = {1, 2};
        changeElement(values);
        System.out.println("Sau changeElement: " + Arrays.toString(values));
        replaceArray(values);
        System.out.println("Sau replaceArray: " + Arrays.toString(values));

        Person person = new Person("Minh");
        rename(person);
        System.out.println("Sau rename: " + person.name);
        replacePerson(person);
        System.out.println("Sau replacePerson: " + person.name);

        String word = "java";
        changeString(word);
        System.out.println("Sau changeString: " + word);

        int[] doubled = doubledCopy(values);
        System.out.println("Mang goc: " + Arrays.toString(values));
        System.out.println("Ban sao gap doi: " + Arrays.toString(doubled));
    }
}
```

Mở terminal tại thư mục chứa tệp. Với **JDK 17 trở lên**, chạy như nhau trên Windows (PowerShell/CMD) hoặc Linux/macOS:

```bash
javac -encoding UTF-8 PassByValueDemo.java
java PassByValueDemo
```

**Kết quả stdout chính xác** (lệnh `javac` thành công không in dòng nào):

```text
Trong changeNumber: 99
Sau changeNumber: 10
Sau changeElement: [99, 2]
Trong replaceArray: [7, 8]
Sau replaceArray: [99, 2]
Sau rename: Lan
Trong replacePerson: Hoa
Sau replacePerson: Lan
Trong changeString: JAVA
Sau changeString: java
Mang goc: [99, 2]
Ban sao gap doi: [198, 4]
```

Các cặp kết quả minh họa ba tình huống khác nhau:

1. **Sửa biến tham số `int`** trong `changeNumber`: giá trị bên ngoài vẫn `10`.
2. **Sửa đối tượng được chia sẻ** trong `changeElement` và `rename`: nội dung mảng và trường của `Person` thực sự thay đổi.
3. **Gán tham số tham chiếu sang đối tượng khác** trong `replaceArray` và `replacePerson`: người gọi tiếp tục dùng đối tượng ban đầu.

Phương thức `doubledCopy` minh họa cách tạo bản sao để tính toán mà không sửa mảng đầu vào.

## 6. Vì sao `String` và `Integer` dễ gây hiểu nhầm?

`String` là **đối tượng bất biến** (*immutable*). Phép `text.toUpperCase()` tạo/trả về một chuỗi tương ứng và không thay đổi đối tượng `String` đã có; phép `text = ...` sau đó chỉ gán lại **tham số cục bộ**. Vì vậy, sau `changeString(word)`, biến `word` của người gọi vẫn giữ giá trị `"java"`.

`Integer` cũng bất biến; thêm vào đó, Java hỗ trợ **autoboxing/unboxing**, khiến cú pháp trông giống đang sửa đối tượng:

```java
static void addOne(Integer value) {
    value++; // Unboxing, tăng int, boxing thành Integer rồi gán lại tham số
}

Integer count = 3;
addOne(count);
// count vẫn bằng 3
```

Đây là mã minh họa bên trong lớp/phương thức. Biểu thức `value++` không sửa đối tượng `Integer` ban đầu. Nếu `value` là `null`, thao tác unboxing này ném `NullPointerException`.

Không nên suy ra rằng “đối số kiểu tham chiếu luôn làm thay đổi biến bên ngoài”: chỉ **phép sửa trạng thái trên cùng đối tượng có thể thay đổi** mới tạo ra ảnh hưởng được quan sát qua tham chiếu khác. Nếu đối tượng bất biến hoặc phương thức chỉ gán lại tham số, đối tượng/biến bên ngoài không đổi.

## 7. Các giới hạn của tham số tham chiếu trong API

`final` cấm **gán lại biến tham số**, không biến object được tham chiếu thành immutable:

~~~java
static void setFirst(final int[] data) {
    data[0] = 5;          // Hợp lệ.
    // data = new int[2]; // Lỗi: final parameter.
}
~~~

Đối số `null` cũng được truyền **theo giá trị**; truy cập `person.name` khi tham số null gây `NullPointerException`. Gán `person = new Person(...)` trong method không thay biến caller vốn đang null.

Muốn trả kết quả mảng mà không sửa nguồn, tạo bản sao rồi **return**; chẳng hạn `int[] copy = input.clone();` với `int[]` tạo mảng mới chứa giá trị primitive độc lập. Với mảng object, `clone()` chỉ **sao chép nông** các tham chiếu phần tử; `int[][].clone()` vẫn chia sẻ các hàng.

Tên API như `sortInPlace` và `sortedCopy` nên nói rõ liệu nó **sửa dữ liệu đầu vào** hay **trả về mảng mới**. Chủ đề này giải thích quy tắc chung cho primitive/reference; bài tham số mảng đi sâu cách sửa phần tử, gán lại hàng của mảng nhiều chiều và sao chép an toàn.


## 8. Lỗi thường gặp và câu hỏi kiểm tra

| Nhận định | Đúng/Sai | Giải thích |
| --- | --- | --- |
| “Java truyền `int` tham trị, nhưng truyền `Person` tham chiếu.” | **Sai** | Cả hai đều truyền tham trị; với `Person`, giá trị được sao chép là tham chiếu. |
| “Gán `person = new Person(...)` sẽ thay biến đối số của bên gọi.” | **Sai** | Chỉ gán lại biến tham số riêng. |
| “`person.name = ...` có thể làm thay đổi đối tượng quan sát ở nơi gọi.” | **Đúng** | Khi cả hai tham chiếu cùng trỏ đến một đối tượng có trạng thái thay đổi được. |
| “Gán `numbers[0] = 99` khác với gán `numbers = new int[]{...}`.” | **Đúng** | Một thao tác thay phần tử của đối tượng mảng chung, thao tác còn lại chỉ thay tham chiếu cục bộ. |
| “Tham số `final int[]` cấm sửa phần tử mảng.” | **Sai** | `final` chỉ cấm gán lại biến tham số. |
| “`String` không đổi sau `text = text.toUpperCase()` trong phương thức vì Java truyền tham trị.” | **Đúng**, với biến bên gọi | `String` bất biến; biến bên gọi vẫn trỏ tới giá trị cũ. |

**Ghi nhớ:** luôn tách ba việc: **(1)** sao chép giá trị của đối số vào tham số, **(2)** sửa trạng thái của đối tượng chung, và **(3)** gán lại chính biến tham số. Chỉ (2) có thể làm dữ liệu được quan sát qua tham chiếu của người gọi thay đổi mà không cần giá trị trả về.