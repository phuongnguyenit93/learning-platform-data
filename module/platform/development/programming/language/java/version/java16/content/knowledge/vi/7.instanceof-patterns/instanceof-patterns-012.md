# Kiểm thử trường hợp khớp kiểu, khác kiểu và null

## 1. Mục tiêu kiểm thử type pattern

Pattern matching for instanceof được chuẩn hóa trong Java 16. Khi kiểm thử mã dùng type pattern, cần xác nhận cả hai phần: phép kiểm tra kiểu trả về kết quả đúng và pattern variable chỉ được dùng trên những đường đi mà pattern đã khớp.

Một bộ kiểm thử nên bao gồm ít nhất ba nhóm đầu vào:

- **Khớp kiểu:** đối tượng thuộc kiểu pattern hoặc một subtype phù hợp; nhánh đúng phải chạy và biến pattern đọc được dữ liệu mong đợi.
- **Khác kiểu:** biểu thức nguồn có kiểu tĩnh đủ tổng quát để phép kiểm tra hợp lệ, nhưng đối tượng thực tế không thuộc kiểu pattern; nhánh đúng không được chạy.
- **null:** phép kiểm tra trả về false, không ném NullPointerException, và chương trình đi theo nhánh mặc định hoặc nhánh xử lý null đã thiết kế.

Ví dụ, biến có kiểu tĩnh Object có thể chứa một chuỗi, một số, một đối tượng StringBuilder hoặc null. Đây là ranh giới phù hợp để kiểm tra các kết quả khác nhau của type pattern.

## 2. Phân biệt không khớp lúc chạy với lỗi biên dịch

Một trường hợp khác kiểu vẫn có thể là ca kiểm thử runtime hợp lệ:

~~~java
Object value = Integer.valueOf(16);

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải chuỗi");
}
~~~

Đoạn mã biên dịch được vì kiểu tĩnh của value là Object. Khi chạy, đối tượng là Integer, nên pattern không khớp và nhánh else được thực thi.

Trường hợp nguồn đã có kiểu tĩnh không thể chuyển kiểu tham chiếu sang kiểu pattern là lỗi biên dịch, không phải ca kiểm thử runtime:

~~~java
Integer value = 16;

// Không biên dịch: Integer không thể khớp String.
// if (value instanceof String text) {
//     ...
// }
~~~

Tương tự, pattern luôn đúng theo kiểu tĩnh nguồn cũng bị từ chối:

~~~java
String value = "Java";

// Không biên dịch: String đã là subtype của CharSequence.
// if (value instanceof CharSequence chars) {
//     ...
// }
~~~

Hãy phân biệt hai loại kiểm tra:

| Loại tình huống | Cách xác minh |
| --- | --- |
| Pattern hợp lệ nhưng đối tượng runtime khác kiểu | Chạy test với nguồn có kiểu tĩnh tổng quát như Object |
| Nguồn là null | Chạy test và xác nhận pattern trả về false |
| Không có casting conversion hoặc pattern luôn đúng | Kiểm tra biên dịch bằng một fixture riêng dự kiến thất bại |

Không đưa đoạn mã cố ý lỗi biên dịch vào cùng file với bộ test chạy được. Nếu muốn kiểm tra quy tắc compiler, đặt ví dụ đó trong file riêng và xác nhận lệnh biên dịch thất bại; không phụ thuộc vào nội dung thông báo lỗi cụ thể vì thông báo có thể khác giữa các phiên bản JDK.

## 3. Viết hàm nhỏ để kiểm tra kết quả khớp, khác kiểu và null

Ví dụ dưới đây phân loại một giá trị. Các nhánh được sắp theo thứ tự cụ thể: String, Number, rồi CharSequence. Một chuỗi khớp cả String và CharSequence, vì vậy phải được nhận ở nhánh String trước.

~~~java
class ValueClassifier {
    static String classify(Object value) {
        if (value instanceof String text) {
            return "text:" + text;
        } else if (value instanceof Number number) {
            return "number:" + number;
        } else if (value instanceof CharSequence sequence) {
            return "sequence:" + sequence.length();
        } else if (value == null) {
            return "null";
        } else {
            return "other:" + value.getClass().getSimpleName();
        }
    }
}
~~~

Kết quả mong đợi:

| Đầu vào | Pattern được chọn | Kết quả |
| --- | --- | --- |
| "Java" | String text | text:Java |
| Integer.valueOf(16) | Number number | number:16 |
| new StringBuilder("Code") | CharSequence sequence | sequence:4 |
| Boolean.TRUE | Không pattern nào khớp | other:Boolean |
| null | Không pattern nào khớp | null |

Ca StringBuilder giúp xác nhận nhánh interface hoạt động. Ca chuỗi giúp phát hiện lỗi đảo thứ tự: nếu CharSequence đứng trước String, kết quả sẽ thay đổi thành sequence:4 đối với chuỗi.

## 4. Bộ kiểm thử Java 16 không cần thư viện ngoài

Có thể tạo một chương trình kiểm thử nhỏ chạy trực tiếp bằng JDK. Cách này phù hợp cho ví dụ học tập hoặc kiểm tra nhanh một hàm trước khi đưa vào dự án có JUnit.

~~~java
import java.util.List;
import java.util.Objects;

public class InstanceofPatternTests {
    interface Printable {
        String print();
    }

    interface Auditable {
        String audit();
    }

    static final class Report implements Printable, Auditable {
        @Override
        public String print() {
            return "printed";
        }

        @Override
        public String audit() {
            return "audited";
        }
    }

    static class Document {
        String title() {
            return "document";
        }
    }

    static final class Invoice extends Document {
        String invoiceNumber() {
            return "INV-16";
        }
    }

    static String classify(Object value) {
        if (value instanceof String text) {
            return "text:" + text;
        } else if (value instanceof Number number) {
            return "number:" + number;
        } else if (value instanceof CharSequence sequence) {
            return "sequence:" + sequence.length();
        } else if (value == null) {
            return "null";
        } else {
            return "other:" + value.getClass().getSimpleName();
        }
    }

    static String dispatch(Object value) {
        if (value instanceof Printable printable) {
            return printable.print();
        } else if (value instanceof Auditable auditable) {
            return auditable.audit();
        }
        return "unsupported";
    }

    static String describeDocument(Object value) {
        if (value instanceof Invoice invoice) {
            return "invoice:" + invoice.invoiceNumber();
        } else if (value instanceof Document document) {
            return "document:" + document.title();
        }
        return value == null ? "null" : "other";
    }

    static String inspectArray(Object value) {
        if (value instanceof String[] words) {
            return "strings:" + words.length;
        } else if (value instanceof int[] numbers) {
            return "ints:" + numbers.length;
        } else if (value instanceof Object[] objects) {
            return "objects:" + objects.length;
        }
        return value == null ? "null" : "other";
    }

    static String inspectList(Object value) {
        if (value instanceof List<?> items) {
            if (items.isEmpty()) {
                return "list:empty";
            }

            Object first = items.get(0);
            if (first instanceof String text) {
                return "list:text:" + text;
            } else if (first instanceof Number number) {
                return "list:number:" + number;
            }
            return "list:other";
        }
        return value == null ? "null" : "other";
    }

    static String requireText(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Expected a non-null String");
        }
        return text.strip();
    }

    static boolean isUsefulText(Object value) {
        return value instanceof String text
                && !text.isBlank()
                && text.length() <= 20;
    }

    static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected <" + expected
                    + "> but was <" + actual + ">");
        }
    }

    static void expectIllegalArgument(String label, Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError(label + ": expected IllegalArgumentException");
    }

    static final class CountingSource {
        private int calls;

        Object next() {
            calls++;
            return calls == 1 ? Integer.valueOf(16) : Integer.valueOf(17);
        }

        int calls() {
            return calls;
        }
    }

    static void checkEvaluationCount() {
        CountingSource source = new CountingSource();

        if (source.next() instanceof String text) {
            System.out.println(text);
        } else if (source.next() instanceof Number number) {
            System.out.println(number);
        }

        checkEquals("Repeated source evaluation", 2, source.calls());
    }

    public static void main(String[] args) {
        Object[][] classifierCases = {
                {"String khớp", "Java", "text:Java"},
                {"Integer khớp Number", Integer.valueOf(16), "number:16"},
                {"StringBuilder khớp interface", new StringBuilder("Code"), "sequence:4"},
                {"Boolean khác kiểu", Boolean.TRUE, "other:Boolean"},
                {"null không khớp", null, "null"}
        };

        for (Object[] testCase : classifierCases) {
            checkEquals((String) testCase[0], testCase[2],
                    classify(testCase[1]));
        }

        checkEquals("Invoice được ưu tiên trước Document",
                "invoice:INV-16", describeDocument(new Invoice()));
        checkEquals("Document khớp kiểu cha",
                "document:document", describeDocument(new Document()));
        checkEquals("Document null",
                "null", describeDocument(null));

        Report report = new Report();
        checkEquals("else-if chỉ chọn nhánh đầu",
                "printed", dispatch(report));
        checkEquals("Không khớp interface",
                "unsupported", dispatch("plain text"));
        checkEquals("null không khớp interface",
                "unsupported", dispatch(null));

        checkEquals("String array",
                "strings:2", inspectArray(new String[] {"A", "B"}));
        checkEquals("Primitive array",
                "ints:3", inspectArray(new int[] {1, 2, 3}));
        checkEquals("Object array",
                "objects:1", inspectArray(new Object[] {"A"}));
        checkEquals("Array null",
                "null", inspectArray(null));

        checkEquals("List of String",
                "list:text:Java", inspectList(List.of("Java", "16")));
        checkEquals("List of Number",
                "list:number:16", inspectList(List.of(16, 17)));
        checkEquals("Empty list",
                "list:empty", inspectList(List.of()));
        checkEquals("List input null",
                "null", inspectList(null));
        checkEquals("Not a list",
                "other", inspectList("Java"));

        checkEquals("Guard clause accepts String",
                "Java", requireText(" Java "));
        expectIllegalArgument("Guard clause rejects Integer",
                () -> requireText(Integer.valueOf(16)));
        expectIllegalArgument("Guard clause rejects null",
                () -> requireText(null));

        checkEquals("&& accepts useful text",
                true, isUsefulText("Java"));
        checkEquals("&& rejects blank text",
                false, isUsefulText("   "));
        checkEquals("&& rejects wrong type",
                false, isUsefulText(16));
        checkEquals("&& rejects null",
                false, isUsefulText(null));

        checkEvaluationCount();
        System.out.println("All instanceof pattern checks passed.");
    }
}
~~~

Lớp test dùng checkEquals và expectIllegalArgument để luôn phát hiện lỗi khi chạy, không phụ thuộc tùy chọn bật/tắt Java assert. Các ca kiểm thử bao gồm:

- Khớp chính xác với String và khớp qua lớp cha Number.
- Khớp qua interface CharSequence.
- Đối tượng sai kiểu và nguồn null.
- Subtype Invoice phải được kiểm tra trước kiểu cha Document.
- Một đối tượng triển khai hai interface nhưng chuỗi else-if chỉ chạy nhánh đầu.
- Mảng tham chiếu, mảng nguyên thủy và mảng Object.
- List<?> với phần tử chuỗi, số, danh sách rỗng và giá trị không phải danh sách.
- Guard clause và điều kiện && khi đầu vào hợp lệ, sai kiểu, chuỗi trắng hoặc null.
- Số lần đánh giá biểu thức nguồn khi lời gọi phương thức xuất hiện trong nhiều nhánh.

## 5. Biên dịch và chạy bộ kiểm thử

Lưu ví dụ thành file InstanceofPatternTests.java, sau đó dùng JDK 16 hoặc mới hơn:

~~~bash
javac --release 16 InstanceofPatternTests.java
java InstanceofPatternTests
~~~

Kết quả khi tất cả ca kiểm thử đạt:

~~~text
17
All instanceof pattern checks passed.
~~~

Lệnh javac với --release 16 yêu cầu trình biên dịch kiểm tra cú pháp và API theo nền tảng Java 16. Có thể chạy bytecode được tạo bằng JDK 16 hoặc JDK mới hơn.

Trong dự án thực tế, nên chuyển các ca kiểm thử này sang framework đang dùng, chẳng hạn JUnit 5, để tích hợp với build và báo cáo test. Giữ nguyên các nhóm dữ liệu đầu vào và kết quả mong đợi; chỉ thay phần harness tự viết bằng assertion và test case của framework.

## 6. Thiết kế test table cho nhiều đầu vào

Khi một hàm nhận Object, bảng ca kiểm thử giúp không bỏ sót những nhóm giá trị khác nhau:

| Nhóm | Ví dụ | Điều cần xác nhận |
| --- | --- | --- |
| Khớp trực tiếp | String | Pattern variable có kiểu đúng và accessor/phương thức chạy được |
| Khớp subtype | Integer với pattern Number | Nhánh lớp cha nhận được lớp con |
| Khớp interface | StringBuilder với CharSequence | Pattern interface hoạt động với lớp triển khai |
| Nhiều kiểu cùng khớp | Invoice cũng là Document | Nhánh cụ thể được kiểm tra trước |
| Khác kiểu | Boolean với các pattern chuỗi/số | Không đi vào nhánh sai |
| Null | null | Pattern trả về false, không phát sinh NPE từ phép kiểm tra |
| Generic | List<?> | Danh sách được nhận diện; từng phần tử được kiểm tra riêng |
| Mảng | String[], int[], Object[] | Phân biệt mảng tham chiếu và mảng nguyên thủy |

Với mỗi hàm phân loại, xác định kết quả mong đợi trước khi viết test. Nếu một đối tượng có thể khớp nhiều pattern, test phải xác nhận chính xác nhánh được chọn, không chỉ xác nhận kết quả khác null.

## 7. Kiểm thử tác dụng phụ và thứ tự đánh giá

Nếu các nhánh gọi phương thức có tác dụng phụ, kiểm tra cả số lần gọi và thứ tự gọi. Ví dụ, khi biểu thức nguồn là một lời gọi phương thức, một chuỗi else-if có thể gọi lại phương thức ở nhánh sau nếu nhánh trước không khớp.

Trong bộ test ở trên, CountingSource trả về một Integer ở lần gọi đầu và một Integer khác ở lần gọi thứ hai. Nhánh String không khớp ở lần đầu, vì vậy nhánh Number gọi next() lần nữa và in ra giá trị 17. Test xác nhận bộ đếm bằng hai.

Nếu thiết kế được thay đổi để lưu kết quả vào một biến Object và kiểm tra cùng một đối tượng, hãy cập nhật kỳ vọng có chủ đích thành một lần gọi. Đừng để số lần đánh giá thay đổi âm thầm trong lúc chỉ định thay cast bằng type pattern.

## 8. Những lỗi thường gặp khi viết test

- **Chỉ kiểm tra ca khớp:** bỏ sót đối tượng sai kiểu và null, khiến nhánh mặc định hoặc guard clause chưa được xác minh.
- **Chỉ kiểm tra kết quả boolean:** không xác nhận nhánh nào được chọn khi đối tượng khớp nhiều kiểu.
- **Dùng kiểu nguồn quá cụ thể:** viết test với biến String rồi thử pattern String hoặc CharSequence sẽ gặp lỗi biên dịch unconditional; hãy dùng Object nếu mục tiêu là kiểm tra pattern ở runtime.
- **Nhầm lỗi compile-time với runtime:** một pattern không có casting conversion không thể được kiểm tra bằng cách chờ nó trả về false.
- **Bỏ qua null bên trong collection:** List<?> có thể chứa phần tử null nếu implementation cho phép; kiểm tra phần tử bằng instanceof sẽ trả về false với phần tử đó.
- **Dựa vào Java assert mà không bật assertion:** chương trình có thể chạy mà không thực hiện các phép kiểm tra. Bộ harness trên dùng AssertionError tường minh để tránh vấn đề này.
- **Không kiểm tra thứ tự:** test một Invoice phải chứng minh nhánh Invoice được chọn trước Document, không chỉ chứng minh hàm trả về một chuỗi nào đó.

**Ghi nhớ:** Bộ test tốt cho instanceof type pattern cần có ca khớp, sai kiểu và null; thêm ca subtype, interface chồng lấp, generic, mảng và flow scope khi hàm sử dụng các cấu trúc đó. Kiểm tra runtime với đầu vào có kiểu tĩnh tổng quát, còn các quy tắc không thể biên dịch phải được xác minh riêng ở bước compiler.
