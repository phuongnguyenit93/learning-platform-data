# Nạp chồng phương thức và những thành phần tạo chữ ký trong Java

> **Java core — language-basics / Phương thức**  
> **Môi trường:** JDK 17+, không cần preview hoặc thư viện ngoài.  
> **Mục tiêu:** Nhận diện những khai báo **overload hợp lệ**, biết thành phần nào thực sự phân biệt **chữ ký phương thức**, hiểu cách Java chọn overload tại thời điểm biên dịch và tránh trùng chữ ký hoặc lời gọi mơ hồ.

## 1. Nạp chồng phương thức là gì?

*Nạp chồng phương thức* (*method overloading*) cho phép một lớp có nhiều phương thức **cùng tên** nhưng có **danh sách kiểu tham số khác nhau**, để biểu diễn những thao tác cùng ý tưởng:

~~~java
static String render(int number) {
    return "int:" + number;
}

static String render(long number) {
    return "long:" + number;
}

static String render(String text) {
    return "String:" + text;
}

static String render(int left, int right) {
    return "pair:" + (left + right);
}
~~~

Những lời gọi sau được phân giải đến các khai báo tương ứng:

~~~java
render(7);        // "int:7"
render(7L);       // "long:7"
render("7");      // "String:7"
render(3, 4);     // "pair:7"
~~~

Tất cả được gọi bằng tên `render`, nhưng trình biên dịch chọn phương thức dựa trên **số đối số, kiểu của biểu thức đối số và quy tắc chọn overload của Java**. Việc sử dụng cùng tên không có nghĩa các phương thức có thể khai báo tùy ý.

Overloading là **chọn giữa các khai báo có chữ ký khác nhau**; không phải *overriding* (ghi đè), nơi lớp con định nghĩa lại phương thức được kế thừa theo các quy tắc riêng.

## 2. Thành phần nào tạo nên chữ ký (*method signature*)?

Trong trường hợp phương thức không generic ở mức nhập môn, hãy xác định chữ ký bằng **tên phương thức + danh sách kiểu tham số theo đúng thứ tự**.

| Thay đổi trong khai báo | Tạo overload khác? | Ví dụ |
| --- | --- | --- |
| Tên giống nhau, **số tham số khác** | Có | `print(int)` và `print(int, int)` |
| Tên giống nhau, **kiểu tham số khác** | Có | `print(int)` và `print(long)` |
| Tên giống nhau, **thứ tự kiểu tham số khác** | Có | `show(int, String)` và `show(String, int)` |
| Chỉ đổi **tên biến tham số** | Không | `calc(int x)` và `calc(int y)` |
| Chỉ đổi **kiểu trả về** | Không | `int calc(int)` và `long calc(int)` |
| Chỉ đổi `public`/`private`, `static` hay `final` | Không | `static calc(int)` và instance `calc(int)` |
| Chỉ đổi khai báo `throws` | Không | `work(int)` và `work(int) throws IOException` |

Hai phương thức cùng lớp không thể tồn tại chỉ nhờ đổi những thành phần **không phân biệt chữ ký**. Ngay cả `static` và instance cũng **không** được khai báo cùng tên, cùng danh sách tham số trong một lớp.

Ví dụ hợp lệ vì **thứ tự tham số khác**:

~~~java
static String combine(int count, String label) {
    return count + "/" + label;
}

static String combine(String label, int count) {
    return label + "/" + count;
}
~~~

Tham số kiểu `int, String` và `String, int` tạo hai chữ ký khác nhau dù cùng có hai tham số. Chỉ hoán đổi **tên** `count`/`label` nhưng giữ nguyên kiểu theo vị trí thì **không** tạo overload.

**Lưu ý phạm vi đặc tả:** Với phương thức *generic*, định nghĩa chữ ký theo Java Language Specification còn xét các tham số kiểu và quy tắc tương đương của kiểu; việc kiểm tra trùng tên/kiểu sau *type erasure* cũng quan trọng. Quy tắc tên + các kiểu tham số ở trên là mô hình đúng cho những ví dụ không generic trong bài.

## 3. Những khai báo không hợp lệ do trùng chữ ký

Các cặp sau là **ví dụ lỗi biên dịch**; không đặt chung vào chương trình runnable:

~~~java
// LỖI 1: chỉ đổi tên tham số.
// static int size(int count) { return count; }
// static int size(int amount) { return amount; }

// LỖI 2: chỉ đổi kiểu trả về.
// static int value(int x) { return x; }
// static String value(int x) { return "" + x; }

// LỖI 3: chỉ đổi static hoặc phạm vi truy cập.
// static int code(int x) { return x; }
// int code(int x) { return x; }

// LỖI 4: chỉ khác throws.
// static int load(int x) { return x; }
// static int load(int x) throws java.io.IOException { return x; }
~~~

Kiểu trả về khác nhau **được phép** nếu danh sách tham số đã khác:

~~~java
static int parseValue(int value) {
    return value;
}

static String parseValue(String value) {
    return value.trim();
}
~~~

Trong hai phương thức trên, sự khác biệt `int` so với `String` ở **tham số** mới là lý do overload hợp lệ; khác kiểu trả về chỉ là lựa chọn của từng phương thức.

**Mảng và varargs:** `int... values` được xem như tham số mảng `int[]` trong chữ ký; không thể khai báo đồng thời `sum(int[])` và `sum(int...)` cùng tên trong cùng lớp:

~~~java
// Chỉ chọn MỘT trong hai khai báo sau:
// static int sum(int[] values) { ... }
// static int sum(int... values) { ... } // Trùng chữ ký với bản trên.
~~~

**Generics và erasure:** `process(List<String>)` không thể overload với `process(List<Integer>)` trong cùng lớp chỉ nhờ đối số kiểu `String`/`Integer`. Cả hai có cùng *erasure* của tham số là `List` và gây *name clash*:

~~~java
// KHÔNG BIÊN DỊCH nếu có cả hai trong cùng lớp:
// static void process(java.util.List<String> a) {}
// static void process(java.util.List<Integer> b) {}
~~~

## 4. Java chọn overload tại thời điểm biên dịch như thế nào?

Trình biên dịch xét các phương thức có tên phù hợp, kiểm tra khả năng áp dụng cho kiểu đối số và chọn phương thức cụ thể nhất theo quy tắc của Java. Có thể ghi nhớ thứ tự xem xét các pha quan trọng:

1. **Lời gọi số đối số cố định, không cần boxing/unboxing** (có thể dùng mở rộng primitive/reference).
2. **Lời gọi cố định cho phép boxing/unboxing** khi pha trước không có phương thức áp dụng.
3. **Lời gọi varargs** khi những pha trước không chọn được phương thức phù hợp.

Ví dụ với mở rộng primitive `int → long` và boxing `int → Integer`:

~~~java
static String select(long value) {
    return "long:" + value;
}

static String select(Integer value) {
    return "Integer:" + value;
}
~~~

| Lời gọi | Chọn overload | Vì sao |
| --- | --- | --- |
| `select(5)` | `select(long)` | Mở rộng `int` thành `long` được xét trước boxing |
| `select(5L)` | `select(long)` | Khớp `long` |
| `select(Integer.valueOf(5))` | `select(Integer)` | Khớp tham chiếu `Integer` |
| `select((Integer) null)` | `select(Integer)` | Kiểu biểu thức là `Integer`; không unbox null |

**Đừng đoán theo “kiểu runtime của đối tượng”:** Lựa chọn overload thông thường dựa trên **kiểu tĩnh của biểu thức ở nơi gọi**. Nếu có `Object value = "Hi";`, lời gọi `label(value)` chọn overload `label(Object)` chứ không tự chuyển sang `label(String)` vì đối tượng thực sự là chuỗi.

Với các overload cùng áp dụng, Java còn dùng quy tắc **most specific**. Nếu không chọn được một phương thức cụ thể nhất, lời gọi bị lỗi **ambiguous** thay vì chạy thử ngẫu nhiên.

## 5. `null`, ép kiểu và lời gọi mơ hồ

Giả sử có hai phương thức:

~~~java
static String label(Object value) {
    return "Object:" + value;
}

static String label(String value) {
    return "String:" + value;
}
~~~

Vì `String` là subtype của `Object`, các kết quả là:

~~~java
label("Hi");              // "String:Hi"
label((Object) "Hi");     // "Object:Hi"
label(null);              // "String:null" (String cụ thể hơn Object).
~~~

Dùng **cast** để làm rõ kiểu biểu thức ở nơi gọi khi cần. Nhưng cast không nên thay thế thiết kế API rõ ràng.

Nếu khai báo một cặp overload có các kiểu **không liên quan theo quan hệ subtype**:

~~~java
// Giả sử đã khai báo:
// static void choose(String text) {}
// static void choose(Integer number) {}

// choose(null);             // LỖI: ambiguous.
// choose((String) null);    // HỢP LỆ: chọn String.
// choose((Integer) null);   // HỢP LỆ: chọn Integer.
~~~

Java không thể chọn một cách duy nhất cho `choose(null)` giữa `String` và `Integer`. Đó là lỗi **ngay khi biên dịch**, không phải `NullPointerException` lúc chạy.

## 6. Varargs và thứ tự pha phân giải overload

Trong chữ ký, `int... values` tương ứng tham số mảng `int[]`: không được khai báo cả `f(int...)` và `f(int[])` cùng tên trong một lớp.

~~~java
static String choose(int value) { return "single:" + value; }
static String choose(int... values) {
    return "count=" + values.length;
}

System.out.println(choose(4));    // single:4.
System.out.println(choose(4, 5)); // count=2.
System.out.println(choose());     // count=0.
~~~

Lời gọi một `int` chọn overload **cố định** khi có phương thức áp dụng ở pha fixed-arity, trước khi cần tới varargs. Nhiều overload varargs với kiểu phần tử không liên quan có thể khiến `f()` hoặc `f(null)` **mơ hồ tại biên dịch**.

Bài này chỉ cần biết varargs **không tạo chữ ký mới** và ảnh hưởng tới lựa chọn overload. Bài varargs/mảng tập trung vào mảng được truyền, `null`, kiểu phần tử là mảng và rủi ro generic varargs.


## 7. Chương trình Java 17+ chạy độc lập

Tạo file **MethodOverloadDemo.java**:

~~~java
public final class MethodOverloadDemo {
    private static String render(int value) {
        return "int:" + value;
    }

    private static String render(long value) {
        return "long:" + value;
    }

    private static String render(String value) {
        return "String:" + value;
    }

    private static String render(int left, int right) {
        return "pair:" + (left + right);
    }

    private static String combine(int count, String label) {
        return count + "/" + label;
    }

    private static String combine(String label, int count) {
        return label + "/" + count;
    }

    private static String select(long value) {
        return "long:" + value;
    }

    private static String select(Integer value) {
        return "Integer:" + value;
    }

    private static String label(Object value) {
        return "Object:" + value;
    }

    private static String label(String value) {
        return "String:" + value;
    }

    private static String aggregate(int... values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return "count=" + values.length + ",sum=" + sum;
    }

    private static String aggregate(int value) {
        return "single:" + value;
    }

    // Hợp lệ: overload main, nhưng launcher chọn main(String[]).
    public static String main(int value) {
        return "main(int):" + value;
    }

    public static void main(String[] args) {
        System.out.println("int=" + render(7));
        System.out.println("long=" + render(7L));
        System.out.println("string=" + render("7"));
        System.out.println("pair=" + render(3, 4));

        System.out.println("orderedA=" + combine(2, "X"));
        System.out.println("orderedB=" + combine("X", 2));

        System.out.println("widen=" + select(5));
        System.out.println("boxed=" + select(Integer.valueOf(5)));
        System.out.println("castNull=" + select((Integer) null));

        Object upcast = "Hi";
        System.out.println("referenceStaticType=" + label(upcast));
        System.out.println("referenceString=" + label("Hi"));
        System.out.println("referenceNull=" + label(null));

        System.out.println("varargsEmpty=" + aggregate());
        System.out.println("varargsMany=" + aggregate(2, 3, 4));
        System.out.println("varargsArray=" + aggregate(new int[] {8, 9}));
        System.out.println("fixedOne=" + aggregate(4));

        System.out.println("otherMain=" + main(3));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 MethodOverloadDemo.java
java MethodOverloadDemo
~~~

**Expected stdout chính xác:**

~~~text
int=int:7
long=long:7
string=String:7
pair=pair:7
orderedA=2/X
orderedB=X/2
widen=long:5
boxed=Integer:5
castNull=Integer:null
referenceStaticType=Object:Hi
referenceString=String:Hi
referenceNull=String:null
varargsEmpty=count=0,sum=0
varargsMany=count=3,sum=9
varargsArray=count=2,sum=17
fixedOne=single:4
otherMain=main(int):3
~~~

`widen=long:5` minh họa mở rộng primitive ưu tiên hơn boxing; `referenceStaticType` cho thấy overload được chọn dựa trên kiểu của biểu thức. `fixedOne` cho thấy bản cố định có thể được ưu tiên hơn varargs. Launcher vẫn chạy `main(String[])` dù lớp có thêm `main(int)`.

## 8. Checklist và bài tập

| Trước khi khai báo overload | Cần kiểm tra |
| --- | --- |
| Tên có trùng nhau không? | Muốn overload thì dùng cùng tên |
| Kiểu/số lượng/thứ tự tham số có khác thật không? | Đây là yếu tố quyết định ở mức nhập môn |
| Chỉ đổi return type hoặc tên tham số? | Không tạo overload hợp lệ |
| Chỉ đổi `static`, access modifier, `throws`? | Không phân biệt chữ ký |
| `int...` so với `int[]`? | Trùng chữ ký, không khai báo cả hai |
| Generic `List<String>` và `List<Integer>`? | Đụng name clash vì erasure |
| Truyền `null` cho hai kiểu tham số không liên quan? | Có thể ambiguous; cân nhắc cast hoặc API rõ hơn |
| Quá nhiều overload nhận kiểu gần nhau? | Thử lời gọi với literal, cast, boxing và varargs |

**Bài 1.** Viết `area(int side)` và `area(int width, int height)` để tính diện tích hình vuông/hình chữ nhật. Nêu hai chữ ký khác nhau ở đâu.

**Bài 2.** Viết `describe(int)`, `describe(long)` và `describe(String)`. Dự đoán lựa chọn khi truyền `4`, `4L` và `"4"`.

**Bài 3.** Giải thích vì sao `void test(int x)` và `int test(int y)` không thể cùng khai báo dù kiểu trả về khác nhau.

**Bài 4.** Viết hai overload nhận `(int, String)` và `(String, int)`; thử truyền đúng và sai thứ tự để thấy kiểm tra tại biên dịch.

**Bài 5.** Tạo `print(Object)` và `print(String)`. Dự đoán lời gọi `print(null)`, `print((Object) "x")` và `print("x")`. Sau đó phân tích lỗi mơ hồ nếu thay `Object` thành `Integer`.

**Bài 6.** Viết `total(int... values)` và gọi với 0, 1, nhiều phần tử hoặc một `int[]`; giải thích vì sao không thể khai báo thêm `total(int[])` với cùng tên.

### Ghi nhớ

**Overloading phân biệt phương thức theo tên và danh sách kiểu tham số (số lượng, kiểu, thứ tự)**; không thể chỉ thay return type, tên tham số, `static` hay `throws`. Java chọn overload dựa vào **kiểu đối số tại thời điểm biên dịch**, theo quy tắc áp dụng và mức độ cụ thể. Chú ý `null` mơ hồ, boxing/varargs và trùng chữ ký sau generic erasure.
