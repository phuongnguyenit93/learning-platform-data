# Boxing trong lựa chọn phương thức nạp chồng

## 1. Cùng giá trị nhưng kiểu đối số có thể chọn phương thức khác

Nạp chồng phương thức (overloading) cho phép nhiều phương thức cùng tên nhưng khác danh sách tham số. Khi một lời gọi có thể dùng boxing, unboxing hoặc chuyển kiểu số, cần biết Java tìm phương thức phù hợp theo cách nào.

Ví dụ hai phương thức:

```java
static String select(long value) {
    return "long";
}

static String select(Integer value) {
    return "Integer";
}
```

Với một đối số `int`, `select` chọn bản nhận `long`; với một đối số có kiểu `Integer`, nó chọn bản nhận `Integer`. Hai biến có thể cùng biểu diễn số 5 nhưng kiểu của biểu thức được truyền vào khác nhau, nên đường lựa chọn khác nhau.

Không nên hình dung trình biên dịch thử mọi cách chuyển rồi gán một “điểm chi phí” cho từng overload. Mô hình đúng cho các ví dụ trong bài là **tìm theo từng giai đoạn**, rồi chọn phương thức cụ thể nhất trong giai đoạn phù hợp đầu tiên.

Những quy tắc này vẫn áp dụng trong Java hiện hành. Các ví dụ chạy bằng JDK 17 trở lên và dùng các phương thức không generic để tập trung vào boxing.

## 2. Ba giai đoạn tìm phương thức phù hợp

| Giai đoạn | Phép chuyển liên quan trong phạm vi bài | Điều kiện chuyển sang giai đoạn sau |
| --- | --- | --- |
| 1 — Lời gọi nghiêm ngặt, số đối số cố định | Giữ nguyên kiểu, mở rộng nguyên thủy, mở rộng tham chiếu; chưa dùng boxing/unboxing | Chưa có phương thức phù hợp ở giai đoạn này |
| 2 — Lời gọi nới lỏng, số đối số cố định | Cho phép thêm boxing/unboxing và các kết hợp được ngữ cảnh lời gọi cho phép | Vẫn chưa có phương thức phù hợp |
| 3 — Lời gọi số đối số thay đổi | Xét cách gọi varargs, gồm các phép chuyển được phép | Nếu không tìm được thì lời gọi lỗi |

Khi đã có các phương thức phù hợp trong một giai đoạn, Java chọn phương thức cụ thể nhất theo quy tắc của ngôn ngữ. Nếu không thể chọn duy nhất, lời gọi có thể lỗi vì mơ hồ; trình biên dịch không đi tiếp chỉ để hy vọng một giai đoạn khác giải quyết ý định của người viết.

Phân biệt **phương thức được khai báo varargs** với **lời gọi dùng cơ chế varargs**. Một phương thức khai báo `int...` có tham số mảng `int[]`; nếu truyền sẵn một mảng phù hợp, nó có thể được xét như lời gọi số đối số cố định ở giai đoạn đầu.

Đối chiếu quá trình tìm overload tại [JLS §15.12.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2).

## 3. Mở rộng nguyên thủy có thể thắng boxing

Với cặp `select(long)` và `select(Integer)` ở đầu bài:

```java
int primitive = 5;
String selected = select(primitive);
```

Đường `int → long` là mở rộng nguyên thủy, phù hợp ở giai đoạn 1. Đường `int → Integer` cần boxing nên chỉ được xét trong giai đoạn sau. Vì đã tìm được bản nhận `long`, bản cần boxing không được đưa vào cùng cuộc so sánh ở giai đoạn đó.

Đây là lý do kết quả là `"long"`, dù `Integer` là wrapper tương ứng với `int`.

Ngược lại:

```java
Integer wrapper = 5;
String selected = select(wrapper);
```

Bản nhận `Integer` phù hợp trực tiếp ở giai đoạn 1. Bản nhận `long` cần mở hộp `Integer → int` rồi mở rộng `int → long`, thuộc giai đoạn sau. Kết quả là `"Integer"`.

Không rút gọn thành “Java luôn thích kiểu nguyên thủy” hay “Java luôn thích wrapper”. Kiểu của đối số và giai đoạn đầu tiên có phương thức phù hợp mới quyết định.

## 4. Mở rộng tham chiếu có thể thắng unboxing

Xét nhóm khác:

```java
static String referenceFirst(Number value) {
    return "Number";
}

static String referenceFirst(long value) {
    return "long";
}
```

Khi truyền một biến `Integer`, mở rộng tham chiếu `Integer → Number` đã hợp lệ ở giai đoạn 1. Phương án mở hộp rồi mở rộng số sang `long` cần giai đoạn 2, nên kết quả chọn bản `Number`.

Như vậy, nhận một wrapper không có nghĩa Java sẽ luôn mở hộp nó trước khi xem những overload tham chiếu khác. Hợp đồng kế thừa giữa các kiểu tham chiếu vẫn được sử dụng trước.

Điều này quan trọng khi thêm một overload mới vào API: một đường gọi trước đây cần unboxing có thể nay tìm được một overload tham chiếu ở giai đoạn sớm hơn. Cần biên dịch và kiểm tra lại các nơi gọi liên quan.

## 5. Khi cần boxing, vẫn phải chọn phương thức cụ thể nhất

Với nhóm:

```java
static String boxedChoice(Integer value) {
    return "Integer";
}

static String boxedChoice(Object value) {
    return "Object";
}
```

Lời gọi `boxedChoice(5)` không phù hợp ở giai đoạn 1: một giá trị `int` không tự là tham chiếu `Integer` hoặc `Object`.

Ở giai đoạn 2, cả hai đều có thể phù hợp: boxing sang `Integer`, hoặc boxing sang `Integer` rồi mở rộng tham chiếu sang `Object`. Trong nhóm ứng viên này, tham số `Integer` cụ thể hơn `Object`, nên chọn bản nhận `Integer`.

Tương tự, nếu hai overload nhận `long` và `double`, còn đối số có kiểu `Integer`, cả hai cần mở hộp rồi chuyển kiểu được phép. Bản nhận `long` cụ thể hơn trong nhóm này vì một giá trị `long` có thể mở rộng thành `double`, còn chiều ngược lại không phải mở rộng nguyên thủy.

Đừng thay quy tắc này bằng câu “boxing luôn có một mức ưu tiên duy nhất”. Sau khi chọn được giai đoạn, vẫn cần giải quyết quan hệ cụ thể nhất giữa các ứng viên.

Tham khảo [JLS §15.12.2.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2.5).

## 6. Boxing và varargs

Với hai overload:

```java
static String spread(Integer value) {
    return "Integer";
}

static String spread(int... values) {
    return "int[]:" + values.length;
}
```

Ba lời gọi khác nhau cho thấy cần nhìn cả dạng đối số:

| Lời gọi | Phương thức được chọn | Vì sao? |
| --- | --- | --- |
| `spread(5)` | Bản `Integer` | Boxing đủ phù hợp ở giai đoạn 2, trước cách gom đối số varargs |
| `spread(new int[] {5, 6})` | Bản `int...` | Mảng đã có phù hợp với tham số `int[]` như lời gọi cố định ở giai đoạn 1 |
| `spread(5, 6)` | Bản `int...` | Cần cách gọi nhiều đối số varargs; bản một `Integer` không đúng số đối số |

Vì vậy câu “varargs luôn được xét cuối” cần hiểu chính xác là **cách gọi số đối số thay đổi** được xét sau. Một khai báo varargs vẫn có thể tham gia sớm với tham số mảng của nó.

## 7. Chương trình chạy đầy đủ

Lưu thành `BoxingOverloadDemo.java`:

```java
public class BoxingOverloadDemo {
    static String select(long value) {
        return "long";
    }

    static String select(Integer value) {
        return "Integer";
    }

    static String referenceFirst(Number value) {
        return "Number";
    }

    static String referenceFirst(long value) {
        return "long";
    }

    static String boxedChoice(Integer value) {
        return "Integer";
    }

    static String boxedChoice(Object value) {
        return "Object";
    }

    static String numeric(long value) {
        return "long";
    }

    static String numeric(double value) {
        return "double";
    }

    static String spread(Integer value) {
        return "Integer";
    }

    static String spread(int... values) {
        return "int[]:" + values.length;
    }

    static String staticChoice(Object value) {
        return "Object";
    }

    static String staticChoice(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        int primitive = 5;
        Integer wrapper = 5;
        Object broad = wrapper;

        System.out.println("primitive select=" + select(primitive));
        System.out.println("wrapper select=" + select(wrapper));
        System.out.println("reference before unboxing=" + referenceFirst(wrapper));
        System.out.println("boxed specificity=" + boxedChoice(primitive));
        System.out.println("unbox then widen=" + numeric(wrapper));

        System.out.println("single before varargs=" + spread(5));
        System.out.println("array argument=" + spread(new int[] {5, 6}));
        System.out.println("multiple arguments=" + spread(5, 6));

        System.out.println("static type choice=" + staticChoice(broad));
        System.out.println("null reference choice=" + select(null));

        Integer absent = null;
        try {
            String selected = numeric(absent);
            System.out.println("unexpected=" + selected);
        } catch (NullPointerException expected) {
            System.out.println("null unboxing=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror BoxingOverloadDemo.java
java BoxingOverloadDemo
```

Stdout:

```text
primitive select=long
wrapper select=Integer
reference before unboxing=Number
boxed specificity=Integer
unbox then widen=long
single before varargs=Integer
array argument=int[]:2
multiple arguments=int[]:2
static type choice=Object
null reference choice=Integer
null unboxing=NullPointerException
```

Nhóm `staticChoice` nhấn mạnh kiểu tĩnh của đối số: biến `broad` có kiểu `Object`, nên lời gọi chọn overload `Object` dù đối tượng nó đang giữ là `Integer`. Lựa chọn overload không phải việc nhìn lớp runtime của từng giá trị để tìm lại toàn bộ nhóm phương thức.

Lời gọi `select(null)` chọn bản tham chiếu `Integer`; thân phương thức chỉ trả nhãn nên không cần mở hộp. Ngược lại, nhóm `numeric` chỉ có những đích số nguyên thủy; truyền biến `Integer` bằng `null` đòi mở hộp, nên gây `NullPointerException` trước khi thân phương thức được chọn có thể xử lý giá trị.

## 8. Mơ hồ và những phép chuyển không được tự ghép

### 8.1. null và hai wrapper không có quan hệ kiểu con

Đoạn phương thức sau cần đặt trong một lớp bao ngoài:

```java
static String ambiguous(Integer value) {
    return "Integer";
}

static String ambiguous(Long value) {
    return "Long";
}

static void demonstrateAmbiguity() {
    // ambiguous(null); // Lỗi biên dịch nếu bỏ chú thích
}
```

`null` phù hợp với cả hai tham số tham chiếu, nhưng `Integer` và `Long` không có quan hệ kiểu con giúp chọn duy nhất bản cụ thể hơn. Không có quyết định dựa trên “wrapper số nhỏ hơn” hoặc thứ tự viết phương thức.

Nếu thật sự muốn một chữ ký cụ thể, một biểu thức có kiểu rõ như `(Integer) null` có thể giải quyết lựa chọn. Việc chọn chữ ký không bảo đảm phần triển khai chấp nhận `null`; cần giữ đúng hợp đồng API.

### 8.2. Nhiều đối số có thể làm hai phương án ngang nhau

Với `mix(int, Integer)` và `mix(Integer, int)`, lời gọi `mix(1, 1)` cần boxing ở một vị trí đối với mỗi ứng viên. Không có quy tắc cộng “số phép boxing” rồi tự chọn theo vị trí đầu tiên; lời gọi mơ hồ vì không có một chữ ký cụ thể hơn chữ ký kia trên toàn bộ các vị trí cần xét.

Thiết kế API tránh những cặp overload dễ mơ hồ thường tốt hơn việc buộc mọi người gọi phải thêm cast để thể hiện ý định.

### 8.3. Không tự mở rộng int rồi boxing thành Long

Nếu chỉ có một phương thức nhận `Long`, truyền một biểu thức `int` không tự hợp lệ nhờ chuỗi `int → long → Long`. Ngữ cảnh lời gọi chỉ cho những kết hợp chuyển đổi được ngôn ngữ quy định.

Có thể truyền `1L`, truyền một biến `long`, hoặc chuyển biểu thức sang `long` rõ ràng khi đó đúng là kiểu dữ liệu mong muốn. Đừng suy từ việc `Integer → int → long` được phép rằng mọi chuỗi kết hợp ngược lại đều được phép.

Các phép chuyển trong ngữ cảnh lời gọi được quy định tại [JLS §5.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.3).

## 9. Cách phân tích một lời gọi có boxing

1. Ghi lại kiểu của từng biểu thức đối số: `int`, `Integer`, `Number`, `Object`, mảng hay `null`.
2. Xác định nhóm phương thức có tên và số tham số phù hợp; với varargs, ghi cả dạng tham số mảng.
3. Kiểm tra giai đoạn đầu chưa cần boxing/unboxing. Nếu đã có ứng viên, chọn cụ thể nhất trong nhóm đó.
4. Chỉ khi chưa có, xét những phép boxing/unboxing hợp lệ trong lời gọi số đối số cố định.
5. Nếu vẫn chưa có, xét cách gọi số đối số thay đổi.
6. Nếu nhiều ứng viên không có một lựa chọn cụ thể nhất, coi đó là lỗi mơ hồ cần sửa khai báo hoặc ý định lời gọi.
7. Sau khi chọn được phương thức, kiểm tra riêng hành vi lúc chạy như mở hộp `null`, nội dung dữ liệu và điều kiện đầu vào.

Đừng chọn overload bằng kiểu dữ liệu đang được in ra hay lớp runtime của một đối tượng. Trong các nhóm phương thức không generic của bài, kiểu tĩnh và quy tắc chuyển đổi của lời gọi là cơ sở cần dùng.

## 10. Tự kiểm tra

1. Với `select(long)` và `select(Integer)`, đối số `int` chọn bản nào?
2. Với `referenceFirst(Number)` và `referenceFirst(long)`, đối số `Integer` chọn bản nào?
3. Vì sao `spread(new int[] {1, 2})` không phải chờ đến giai đoạn gom đối số varargs?
4. `ambiguous(Integer)` và `ambiguous(Long)` có tự chọn được khi truyền literal `null` không?
5. Chọn được overload có bảo đảm lời gọi không gây `NullPointerException` do unboxing không?

Đáp án:

1. Bản nhận `long`, vì mở rộng nguyên thủy phù hợp trước giai đoạn cần boxing.
2. Bản nhận `Number`, vì mở rộng tham chiếu phù hợp trước giai đoạn cần unboxing.
3. Đối số đã là mảng phù hợp với tham số `int[]`, nên có thể xét như lời gọi cố định.
4. Không. Hai kiểu wrapper không tạo được một lựa chọn cụ thể hơn duy nhất cho `null`.
5. Không. Việc chọn chữ ký và việc thực hiện chuyển đổi giá trị lúc chạy là hai bước cần phân biệt.

Hãy tìm giai đoạn phù hợp đầu tiên, rồi giải quyết tính cụ thể nhất trong giai đoạn đó. Cách đọc này đáng tin hơn một khẩu quyết coi boxing, mở rộng số và varargs là những điểm ưu tiên có thể cộng tùy ý.
