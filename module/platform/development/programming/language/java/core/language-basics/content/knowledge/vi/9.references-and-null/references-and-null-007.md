# `null` biểu thị không tham chiếu tới đối tượng — Java 17+

Trong Java, `null` là **giá trị đặc biệt của kiểu tham chiếu**, có nghĩa **biến không tham chiếu tới bất kỳ đối tượng nào**. `null` không phải một đối tượng “rỗng”, cũng không phải địa chỉ của một đối tượng có dữ liệu mặc định.

~~~java
Ticket missing = null;                  // Khong tro toi Ticket nao.
Ticket present = new Ticket("A1");      // Tro toi mot Ticket duoc tao.
Ticket same = present;                  // Hai bien tro cung Ticket.
~~~

Hệ quả quan trọng:

- Có thể so sánh `missing == null` một cách an toàn.
- Không thể gọi phương thức instance hoặc truy cập field qua tham chiếu `null`: thao tác đó gây `NullPointerException`.
- Gán `present = null` chỉ thay giá trị tham chiếu trong **biến `present`**; nếu `same` vẫn trỏ tới đối tượng, đối tượng vẫn tồn tại và có thể được dùng qua `same`.
- Kiểu nguyên thủy như `int` hoặc `boolean` không được gán trực tiếp `null`.

## 1. Phân biệt `null` với đối tượng và chuỗi rỗng

| Ví dụ | Có đối tượng thực sự được tham chiếu không? | Ý nghĩa |
| --- | --- | --- |
| `Ticket t = null;` | **Không** | Biến `t` không tham chiếu Ticket nào |
| `Ticket t = new Ticket("");` | **Có** | Một Ticket thật, thuộc tính chuỗi có thể rỗng |
| `String s = null;` | **Không** | Không có đối tượng String qua biến `s` |
| `String s = "";` | **Có** | Đối tượng String có `length() == 0` |
| `String s = " ";` | **Có** | Chuỗi chứa một dấu cách, độ dài 1 |
| `Ticket[] a = new Ticket[2];` | **Có, một đối tượng mảng** | Hai **phần tử tham chiếu** ban đầu bằng `null` |
| `int n = 0;` | Không liên quan `null` | Giá trị nguyên thủy số 0 |

`null` **không đồng nghĩa** với số `0`, `false`, chuỗi `""` hoặc một đối tượng có các field bằng giá trị mặc định. Nên quyết định rõ khi thiết kế API: liệu `null` mang nghĩa “chưa cung cấp”, “không tìm thấy” hay “không áp dụng”, thay vì dùng tùy tiện.

## 2. Chương trình Java 17+ chạy được

Lưu tệp UTF-8 tên **`NullReferenceDemo.java`**:

~~~java
public class NullReferenceDemo {
    static class Ticket {
        final String id;

        Ticket(String id) {
            this.id = id;
        }

        String describe() {
            return "Ticket(" + id + ")";
        }
    }

    static Ticket shared; // Static reference field mac dinh null.

    static class Holder {
        Ticket ticket;     // Instance reference field mac dinh null.
    }

    static void reassignParameter(Ticket local) {
        local = null;      // Chi gan lai bien tham so.
        System.out.println("insideParamNull=" + (local == null));
    }

    public static void main(String[] args) {
        Ticket absent = null;
        System.out.println("absentNull=" + (absent == null));
        System.out.println("sharedNull=" + (shared == null));

        Holder holder = new Holder();
        System.out.println("fieldNull=" + (holder.ticket == null));

        Ticket[] tickets = new Ticket[2];
        System.out.println("slotNull=" + (tickets[0] == null));

        Ticket original = new Ticket("A1");
        Ticket alias = original;
        tickets[0] = original;
        System.out.println("aliasSame=" + (alias == original));

        original = null;
        System.out.println("originalNull=" + (original == null));
        System.out.println("aliasExists=" + alias.describe());

        reassignParameter(alias);
        System.out.println("aliasAfterMethod=" + alias.describe());

        Ticket empty = new Ticket("");
        System.out.println("emptyObjectNull=" + (empty == null));

        String emptyText = "";
        String absentText = null;
        System.out.println("emptyStringNull=" + (emptyText == null));
        System.out.println("emptyStringLength=" + emptyText.length());
        System.out.println("safeEquals=" + "Java".equals(absentText));
        System.out.println(
                "guard=" + (absentText == null || absentText.isBlank()));

        try {
            System.out.println(absent.describe());
        } catch (NullPointerException ex) {
            System.out.println("dereference=NullPointerException");
        }

        Integer wrapper = null;
        try {
            int value = wrapper;
            System.out.println("unboxed=" + value);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }

        System.out.println("arrayAlias=" + (tickets[0] == alias));
    }
}
~~~

Trong PowerShell (Windows) hoặc Bash (Linux/macOS), chuyển tới thư mục chứa tệp và chạy bằng **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NullReferenceDemo.java
java NullReferenceDemo
~~~

**Expected output** của lệnh `java NullReferenceDemo`:

~~~text
absentNull=true
sharedNull=true
fieldNull=true
slotNull=true
aliasSame=true
originalNull=true
aliasExists=Ticket(A1)
insideParamNull=true
aliasAfterMethod=Ticket(A1)
emptyObjectNull=false
emptyStringNull=false
emptyStringLength=0
safeEquals=false
guard=true
dereference=NullPointerException
unboxing=NullPointerException
arrayAlias=true
~~~

Các dòng `java -version` và `javac -version` phụ thuộc JDK đã cài, nên không thuộc khối expected output cố định.

### Vì sao kết quả như vậy?

1. `absent = null` không trỏ tới Ticket; kiểm tra bằng `== null` hợp lệ và trả `true`.
2. Field `shared`, `holder.ticket` và phần tử `tickets[0]` mặc định bằng `null` khi chưa được gán đối tượng. **Mảng `tickets` vẫn là một đối tượng đã được tạo**.
3. `alias = original` và `tickets[0] = original` sao chép **giá trị tham chiếu**. Cả ba lối truy cập ban đầu cùng dẫn tới Ticket("A1").
4. `original = null` không xóa Ticket("A1"): `alias` và `tickets[0]` vẫn trỏ tới đối tượng. Vì vậy `alias.describe()` còn chạy được.
5. Phương thức `reassignParameter` nhận bản sao tham chiếu; `local = null` không làm biến `alias` ở bên gọi biến thành null. Java **truyền tham số theo giá trị**.
6. `new Ticket("")` tạo một Ticket thực sự dù `id` là chuỗi rỗng. Chuỗi `""` cũng là một String thật có độ dài 0, khác `String absentText = null`.
7. `"Java".equals(absentText)` an toàn vì đối tượng nhận lời gọi là literal không null; kết quả là `false`. Biểu thức `absentText == null || absentText.isBlank()` dùng *short-circuit*, nên không gọi `isBlank()` trên null.
8. `absent.describe()` gây `NullPointerException`. `Integer wrapper = null` hợp lệ nhưng tự động **unboxing** `wrapper` sang `int` cũng gây `NullPointerException`.

## 3. Vì sao `null` và biến cục bộ chưa khởi tạo khác nhau?

~~~java
Ticket later;
// System.out.println(later); // Sai: bien cuc bo chua duoc gan.

later = null;
System.out.println(later == null); // Hop le: true.
~~~

- **Biến cục bộ chưa được gán chắc chắn:** compiler không cho phép đọc giá trị, theo quy tắc *definite assignment*.
- **Biến đã được gán `null`:** đọc biến và so sánh với `null` đều hợp lệ, nhưng không thể truy cập thành viên instance qua tham chiếu đó.
- **Field kiểu tham chiếu:** nếu không có initializer hoặc phép gán khác, nó nhận giá trị mặc định `null`. Điều này **không** có nghĩa Java tự tạo đối tượng cho field.

Ví dụ một class có field `Ticket ticket;` không tự tạo `Ticket` khi đối tượng chứa field được tạo. Nếu muốn có Ticket thật, phải thực hiện thao tác khởi tạo phù hợp, chẳng hạn `ticket = new Ticket("A1");`.


## 4. Kiểm tra `null` theo mục đích

- `x == null` và `x != null` kiểm tra tham chiếu một cách an toàn. Muốn dùng member, phải có giá trị khác `null`.
- `x != null && x.describe().isEmpty()` tận dụng short-circuit: vế phải chỉ chạy khi `x` có đối tượng.
- `"OK".equals(s)` và `Objects.equals(a, b)` hỗ trợ so sánh an toàn khi dữ liệu có thể vắng mặt; lưu ý hai đối số đều `null` thì `Objects.equals` trả `true`.
- `Objects.requireNonNull(x, "x required")` chủ động báo vi phạm khi hợp đồng yêu cầu có object. Đây là lựa chọn thiết kế, không phải cách chữa mọi lỗi.
- Với wrapper như `Integer`, kiểm tra trước khi tự động unbox để tránh `NullPointerException`.

## 5. `null` không phải “lệnh xóa” đối tượng

~~~java
Ticket a = new Ticket("A1");
Ticket b = a;

a = null; // Chi doi gia tri trong bien a.
System.out.println(b.describe()); // Van goi duoc.
~~~

Sau `a = null`, biến `b` vẫn tham chiếu đối tượng. **Việc đối tượng còn được truy cập hay không** phụ thuộc mọi tham chiếu còn tồn tại, không chỉ một biến. Java dùng garbage collector; không có bảo đảm “gán null là đối tượng bị thu gom ngay”.

Điều này cũng khác với **đóng tài nguyên**: một đối tượng giữ file, kết nối hoặc socket có thể cần `close()`/`try-with-resources` theo hợp đồng API. Chỉ gán tham chiếu thành null không thay cho việc giải phóng các tài nguyên ngoài bộ nhớ.

### `final` không loại bỏ khả năng có null

~~~java
final Ticket chosen = null;

// chosen = new Ticket("A1"); // Sai: chosen da duoc gan va la final.
~~~

`final` chỉ giới hạn **việc gán lại biến**, không tự yêu cầu biến phải chứa đối tượng. Một tham chiếu `final` có thể mang `null` nếu được khởi tạo hợp lệ như trên.

## 6. Những nhận định dễ nhầm

| Nhận định | Đúng hay sai? | Lý do |
| --- | --- | --- |
| “`null` là một đối tượng Ticket có dữ liệu trống.” | **Sai** | Không tham chiếu đối tượng nào |
| “`Ticket t = null;` tạo Ticket.” | **Sai** | Chỉ gán giá trị tham chiếu null |
| “`Ticket t;` trong phương thức mặc định bằng null.” | **Sai** | Local phải được gán chắc chắn trước khi đọc |
| “Field `Ticket t;` chưa gán mặc định là null.” | **Đúng** | Giá trị mặc định của reference field |
| “`new Ticket[2]` tạo hai Ticket.” | **Sai** | Tạo một mảng gồm hai phần tử null |
| “Gán `t = null` chắc chắn xóa đối tượng ngay.” | **Sai** | Các tham chiếu khác có thể còn tồn tại |
| “`t == null` gây NPE khi t là null.” | **Sai** | So sánh null là an toàn |
| “`t.describe()` khi t là null gây NPE.” | **Đúng** | Không có đối tượng để truy cập |
| “`Integer n = null; int x = n;` luôn an toàn.” | **Sai** | Unboxing null gây NPE |
| “`final Ticket t = null;` hợp lệ.” | **Đúng** | `final` không cấm giá trị null |

## 7. Bài tập tự kiểm tra

**Bài 1.** Sau `Ticket a = null;`, `a == null` là gì? `a.describe()` có chạy được không?

*Đáp án:* `true`; gọi `describe()` gây `NullPointerException`.

**Bài 2.** `Ticket a = new Ticket("A"); Ticket b = a; a = null;`. `b` còn dùng được không?

*Đáp án:* Có. `b` vẫn tham chiếu Ticket("A").

**Bài 3.** `String a = null; String b = "";` có tương đương không?

*Đáp án:* Không. `a` không trỏ đối tượng, `b` là đối tượng String rỗng có `length() == 0`.

**Bài 4.** Vì sao `Ticket[] t = new Ticket[3];` có `t[0] == null` dù mảng `t` đã được tạo?

*Đáp án:* Bản thân mảng là đối tượng; các **phần tử kiểu tham chiếu** chưa gán nhận null, không tự tạo Ticket.

**Bài 5.** Tại sao `Integer n = null;` hợp lệ nhưng `int x = n;` có thể ném lỗi?

*Đáp án:* `Integer` là reference type và có thể null; tự động unboxing cần giá trị đối tượng thật nên ném `NullPointerException` khi null.

## Checklist

- [ ] Hiểu `null` nghĩa là **không tham chiếu tới đối tượng**, không phải “đối tượng rỗng”.
- [ ] Phân biệt null với `""`, `0` và đối tượng được khởi tạo.
- [ ] Biết field/array reference defaults khác local variable chưa definite assignment.
- [ ] Kiểm tra `== null` hoặc `!= null` an toàn trước khi gọi thành viên instance.
- [ ] Hiểu gán null chỉ đổi tham chiếu của **biến**, không tự xóa object.
- [ ] Nhận biết lỗi NPE khi dereference hoặc unboxing wrapper null.
- [ ] Dùng short-circuit, null-safe equality, yêu cầu non-null theo hợp đồng API.

**Kết luận:** `null` là **giá trị của tham chiếu không trỏ tới đối tượng nào**. Khi viết Java, hãy tách biệt **sự tồn tại của biến**, **giá trị tham chiếu trong biến** và **sự tồn tại của đối tượng**. Kiểm tra null đúng nơi giúp tránh `NullPointerException` và tránh nhầm null với dữ liệu rỗng.
