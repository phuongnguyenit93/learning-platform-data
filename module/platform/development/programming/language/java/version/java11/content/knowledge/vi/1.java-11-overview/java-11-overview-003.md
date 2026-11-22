# Phân biệt hợp đồng API với chi tiết triển khai của JDK

> **Bối cảnh:** Định hướng sử dụng Java 11 và các phiên bản Java hiện đại. Nguyên tắc ở đây vẫn áp dụng khi nâng cấp JDK hoặc đổi nhà cung cấp JVM: chỉ dựa vào những hành vi được tài liệu của API/đặc tả phiên bản mục tiêu cam kết.

## 1. Hai khái niệm cần phân biệt

**Hợp đồng API (API contract)** là tập hợp các điều kiện và hành vi mà người sử dụng một API được phép trông đợi: cách gọi, kiểu dữ liệu, giá trị trả về, thứ tự (nếu được cam kết), quy tắc với `null`, khả năng sửa đổi, ngoại lệ, tính an toàn luồng và các điều kiện khác được đặc tả. Hợp đồng có thể nằm ở tài liệu của interface, class cụ thể, phương thức hoặc đặc tả Java SE.

**Chi tiết triển khai (implementation detail)** là cách một bản JDK hiện thực hành vi đó: cấu trúc dữ liệu bên trong, thuật toán cụ thể, lớp nội bộ, cách bố trí bộ nhớ, chiến lược JIT/GC, lịch chạy luồng, tối ưu hóa hoặc giá trị phụ thuộc môi trường. Chi tiết này có thể thay đổi khi nâng cấp JDK, đổi JVM, đổi cấu hình hoặc đổi dữ liệu đầu vào mà API vẫn hoàn toàn đúng hợp đồng.

| Tiêu chí | Hợp đồng API | Chi tiết triển khai |
| --- | --- | --- |
| Câu hỏi | “API **cam kết** điều gì?” | “Bản JDK này **đang thực hiện** như thế nào?” |
| Nguồn xác nhận | Đặc tả Java SE, Javadoc công khai đúng phiên bản, quy định rõ của API | Mã nguồn JDK, debugger, benchmark, quan sát khi chạy, lớp hoặc trường nội bộ |
| Mức có thể dựa vào | Có, trong phạm vi phiên bản, điều kiện và loại API đã công bố | Chỉ khi ứng dụng chủ động chấp nhận phụ thuộc vào triển khai cụ thể |
| Ví dụ | `List.copyOf` trả về danh sách không thể sửa qua API; `HashMap` không hứa thứ tự duyệt | Tên class nội bộ của danh sách, kích thước bảng băm, thứ tự `HashMap` tình cờ thấy trên máy |
| Khi thay JDK | Hành vi đặc tả vẫn phải được tôn trọng trong phạm vi tương thích | Có thể khác mà không phải lỗi của JDK |

**Điểm mấu chốt:** “Chạy đúng trên máy tôi” là một quan sát, không tự biến thành một lời hứa của API. Ngược lại, không phải mọi đặc điểm của một class cụ thể đều là chi tiết không đáng tin: nếu tài liệu class cam kết rõ một đặc điểm, đó chính là hợp đồng của class ấy.

## 2. Ranh giới: ngôn ngữ Java, API và bản JDK

- **Java Language Specification (JLS)** quy định các quy tắc của ngôn ngữ, chẳng hạn kiểu, biểu thức, ngoại lệ và mô hình bộ nhớ Java.
- **Java Virtual Machine Specification (JVMS)** quy định các yêu cầu của máy ảo và định dạng, thực thi class file.
- **Java SE API Specification** quy định hợp đồng của những API Java SE công khai, chẳng hạn `java.util.List`, `java.util.Map` và `java.lang.String`.
- **JDK cụ thể** cung cấp trình biên dịch, thư viện, công cụ, máy ảo và các lựa chọn thực hiện những quy tắc trên. JDK có thể có thêm API/công cụ riêng; tính “công khai” hoặc “có thể import” của một tên không tự chứng minh nó thuộc hợp đồng Java SE.

Ví dụ, từ kiểu `Map<K,V>` ta biết cách làm việc với ánh xạ khóa–giá trị theo hợp đồng `Map`. Khi chọn `HashMap`, ta có thêm những đặc điểm được Javadoc của `HashMap` công bố (như chấp nhận một khóa `null`); ta **không** có quyền suy ra thứ tự duyệt chỉ vì máy hiện tại thường cho ra cùng một thứ tự. Khi chọn `LinkedHashMap` ở chế độ mặc định, thứ tự chèn được class ấy bảo đảm. Hợp đồng cần được đọc ở **đúng cấp abstraction** đang sử dụng.

Một hành vi “không được đặc tả” không nhất thiết là ngẫu nhiên hay luôn thay đổi. Nó chỉ có nghĩa rằng chương trình đúng không được yêu cầu hành vi ấy phải luôn giống nhau.

## 3. Cách đọc Javadoc để xác định điều được bảo đảm

Đối với API cần dùng, đọc tài liệu **đúng phiên bản JDK mục tiêu** và theo trình tự:

1. **Mô tả của interface/class**, rồi đến phương thức được gọi: đọc cả điều kiện trước khi gọi và điều kiện sau khi trả về.
2. **`@param`, `@return`, `@throws`**: xác định tham số hợp lệ, ý nghĩa kết quả, ngoại lệ đã quy định; đừng dựa vào thông điệp ngoại lệ hoặc số dòng stack trace nếu tài liệu không hứa.
3. **Ghi chú về `null`, thứ tự, khả năng sửa đổi và đa luồng**: đôi khi các quy tắc quan trọng nằm ở phần mô tả chung của class/interface, không nằm ngay dưới phương thức.
4. **Các từ có điều kiện** như “may”, “optional”, “if”, “generally”, “typically” và “unspecified”: chúng không đồng nghĩa với một bảo đảm vô điều kiện.
5. **`Since`, `Deprecated`, phiên bản tài liệu và loại API**: API tồn tại ở JDK mới chưa chắc đã có trong Java 11; một API được công bố thử nghiệm/preview hoặc gắn riêng với JDK cần đánh giá theo phạm vi hỗ trợ của chính nó.

Trong tài liệu JDK, các nhãn còn có ý nghĩa khác nhau:

| Nhãn Javadoc | Cách hiểu thực tế |
| --- | --- |
| Mô tả API chính và các mục `Parameters`, `Returns`, `Throws` | Hợp đồng mà mã gọi API cần tuân thủ trong phạm vi đã mô tả |
| **API Note** (`@apiNote`) | Giải thích, lời khuyên sử dụng, ví dụ; đọc để hiểu API nhưng phân biệt với các cam kết cụ thể |
| **Implementation Requirements** (`@implSpec`) | Mô tả yêu cầu/hành vi của triển khai mặc định hoặc phương thức có thể ghi đè; đặc biệt hữu ích khi **triển khai/override**; không áp đặt máy móc lên mọi bản override khác |
| **Implementation Note** (`@implNote`) | Thông tin về cách triển khai cụ thể; không tự nâng nó thành hợp đồng cho mọi JDK/phiên bản |

Chẳng hạn, `List.copyOf` được **phần mô tả API** cam kết trả về một `List` không thể sửa, giữ thứ tự duyệt của `Collection` đầu vào và không phản ánh những thay đổi sau này ở collection nguồn. Phần **Implementation Note** có thể nói việc gọi với một danh sách vốn đã không thể sửa thường không tạo bản sao mới. Điều người gọi cần tin là **ngữ nghĩa của kết quả**, không phải việc cấp phát một object mới hay trả lại object cũ.

## 4. Các ví dụ dễ nhầm trong Java thực tế

### 4.1. `HashMap`: ánh xạ đúng, thứ tự duyệt không có bảo đảm

**Được bảo đảm theo tài liệu:** `HashMap` ánh xạ khóa tới giá trị, hỗ trợ các phép toán được mô tả và cho phép khóa/giá trị `null`. **Không được bảo đảm:** thứ tự mà `entrySet()`, `keySet()` hoặc `values()` được duyệt; thứ tự ấy cũng không được hứa sẽ giữ nguyên theo thời gian.

Sai về mặt thiết kế:

~~~java
Map<String, Integer> scores = new HashMap<>();
scores.put("B", 2);
scores.put("A", 1);
System.out.println(scores); // Không được giả định luôn là "{A=1, B=2}"
~~~

Chọn giải pháp theo nhu cầu:

- Muốn **thứ tự chèn**: dùng `LinkedHashMap` ở chế độ chèn mặc định.
- Muốn **thứ tự khóa**: dùng `TreeMap` với thứ tự tự nhiên hoặc comparator phù hợp.
- Chỉ muốn xuất danh sách có thứ tự nhất quán: **sort tường minh** trước khi xuất. Việc chọn thứ tự là yêu cầu của ứng dụng, không phải việc dò đoán cách `HashMap` chia bucket.

Cũng không nên thử một lần rồi kết luận rằng “`HashMap` của Java 11 luôn duyệt theo thứ tự khóa”, vì dữ liệu thử, hàm băm và cách triển khai có thể tạo ảo giác ổn định.

### 4.2. `List.copyOf`: bảo đảm tính không thể sửa qua API, không hứa class nội bộ

`List.copyOf(source)` (có từ Java 10) tạo một `List` không thể sửa qua các phương thức sửa đổi của danh sách; thứ tự phần tử theo thứ tự duyệt nguồn; nguồn thay đổi sau đó không làm danh sách kết quả tự thay đổi. Nếu đầu vào chứa `null`, thao tác tạo danh sách sẽ báo `NullPointerException`.

Không nên suy đoán:

- Tên class mà `copy.getClass().getName()` trả về.
- `copy` và `source` có cùng danh tính object hay không; tài liệu cho phép tái sử dụng một danh sách nguồn đã không thể sửa.
- Danh sách “bất biến sâu”. Nếu phần tử là object có thể thay đổi, thay đổi **trạng thái phần tử** vẫn có thể được quan sát qua danh sách.

Phân biệt thêm: `Collections.unmodifiableList(source)` trả về một **view** không sửa được qua view, nhưng thay đổi của `source` vẫn thấy qua view. `List.copyOf(source)` thì tách khỏi những thay đổi thêm/xóa/thay phần tử của collection nguồn. Cả hai đều không tự sao chép sâu object phần tử.

### 4.3. `Map.get` trả về `null`: không đủ để kết luận khóa vắng mặt

Với một `Map` cho phép giá trị `null`, `map.get(key) == null` có thể xảy ra khi **không có khóa** hoặc **có khóa nhưng ánh xạ tới `null`**. Nếu ứng dụng phải phân biệt hai trường hợp, dùng `containsKey(key)` theo hợp đồng, không đoán dựa trên kết quả `get`.

Đọc cả tài liệu class cụ thể: `HashMap` cho phép `null`, còn không thể suy rộng quy tắc này cho mọi triển khai `Map`.

### 4.4. Hiệu năng, nội bộ và môi trường không phải lời hứa vô điều kiện

- Tài liệu `HashMap` nói hiệu năng kỳ vọng gần hằng số cho một số phép toán **với giả định** hàm băm phân tán hợp lý; không có nghĩa mọi thao tác luôn mất đúng O(1) trong mọi đầu vào.
- GC, JIT, cache, layout object, kích thước bộ nhớ, tên class nội bộ và số lượng CPU mà JVM quan sát đều có thể phụ thuộc vào JDK, hệ điều hành hoặc cấu hình.
- Không yêu cầu hai thread chạy theo đúng thứ tự quan sát được trong một lần debug; muốn bảo đảm thứ tự/khả năng nhìn thấy dữ liệu, dựa trên quy tắc happens-before và công cụ đồng bộ được Java đặc tả (`synchronized`, `volatile`, các API đồng bộ phù hợp).
- Không assert chính xác thông điệp lỗi, thời gian chạy, thứ tự một `HashMap`, hay thứ tự chạy thread nếu tài liệu không xác nhận chúng là đầu ra bắt buộc.

Các quan sát và tối ưu đó vẫn có ích cho **chẩn đoán/benchmark**, nhưng không nên biến thành điều kiện đúng/sai của logic nghiệp vụ.

## 5. Chương trình Java có thể chạy: kiểm tra hợp đồng thay vì đoán implementation

Tạo tệp **`ApiContractDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ApiContractDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new HashMap<>();
        scores.put("B", 2);
        scores.put("A", 1);

        // HashMap không hứa thứ tự duyệt. Sort để bảo đảm đầu ra.
        List<String> ordered = scores.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .map(entry -> entry.getKey() + "=" + entry.getValue())
                .collect(Collectors.toList());
        System.out.println(ordered);

        List<String> source = new ArrayList<>(List.of("B", "A"));
        List<String> copy = List.copyOf(source);
        List<String> view = Collections.unmodifiableList(source);
        source.add("C");

        // Copy tách khỏi các thay đổi ở cấu trúc collection nguồn.
        System.out.println("copy=" + copy);

        // View nhìn thấy thay đổi ở collection nguồn.
        System.out.println("view=" + view);

        try {
            copy.add("D");
        } catch (UnsupportedOperationException ex) {
            // Chỉ dựa vào loại ngoại lệ, không dựa vào message.
            System.out.println("UnsupportedOperationException");
        }

        Map<String, Integer> nullable = new HashMap<>();
        nullable.put("present", null);
        System.out.println(nullable.containsKey("present"));
        System.out.println(nullable.containsKey("missing"));
    }
}
~~~

Biên dịch và chạy bằng JDK hỗ trợ Java 11 trở lên:

~~~bash
javac --release 11 ApiContractDemo.java
java ApiContractDemo
~~~

**Stdout chính xác:**

~~~text
[A=1, B=2]
copy=[B, A]
view=[B, A, C]
UnsupportedOperationException
true
false
~~~

**Vì sao kết quả này đáng tin:**

1. Danh sách `ordered` được **sort rõ ràng** theo khóa, nên đầu ra không phụ thuộc thứ tự duyệt của `HashMap`.
2. `List.copyOf` giữ thứ tự `B, A` của nguồn lúc tạo và không phản ánh thao tác `source.add("C")`; `unmodifiableList` là view nên thấy thêm `C`.
3. Phép `copy.add("D")` phải ném `UnsupportedOperationException`; ta không in message hay stack trace vì chúng không cần ổn định.
4. `containsKey` phân biệt khóa `present` có giá trị `null` với khóa `missing` không tồn tại.
5. Chương trình chỉ dùng API có sẵn trong Java 11. `--release 11` giúp kiểm tra API và cú pháp tại mức phát hành mục tiêu khi dùng JDK mới hơn; vẫn cần chạy thử trên runtime dự định triển khai.

Lưu ý: đoạn minh họa ngắn riêng tại mục 4.1 **không phải** chương trình Java độc lập. Tệp ở mục này mới là ví dụ hoàn chỉnh có `main` và lệnh chạy.

## 6. Chuyển JDK, kiểm thử và review đúng cách

Một thay đổi có thể **tương thích hợp đồng** dù quan sát bên ngoài khác nhau. Ví dụ, một bản JDK mới thay class nội bộ mà `List.of` tạo ra, hoặc làm `HashMap` duyệt theo thứ tự khác, vẫn hợp lệ nếu giữ các cam kết API. Ngược lại, nếu API nói duy trì thứ tự chèn mà triển khai vi phạm, đó mới là dấu hiệu lỗi so với hợp đồng đã công bố.

Khi nâng cấp runtime từ Java 11 hoặc chuyển sang một JDK hiện đại:

1. **Chốt phiên bản mục tiêu:** đọc Javadoc tương ứng với phiên bản biên dịch/chạy; kiểm tra `Since` cho API mới và thông tin loại bỏ/thay đổi API nếu có. Với dự án hỗ trợ Java 11, tránh vô tình gọi API chỉ xuất hiện ở bản phát hành mới.
2. **Ưu tiên API chuẩn và ổn định:** chỉ dùng API JDK-specific/preview/incubator khi yêu cầu cho phép và đã kiểm tra phạm vi hỗ trợ. Các tên `jdk.internal.*` hoặc những đường truy cập sâu vào runtime không phải lựa chọn mặc định cho logic ứng dụng.
3. **Loại bỏ việc phụ thuộc vào quan sát tình cờ:** không dựa vào phản chiếu trường private của JDK, thứ tự `HashMap`, class nội bộ của `List.of`, bytecode/JIT cụ thể, hay khác biệt thông điệp exception.
4. **Viết test theo ngữ nghĩa:** kiểm giá trị/kiểu ngoại lệ/quan hệ thứ tự được cam kết. Với container không cam kết thứ tự, so sánh theo tập hợp hoặc sort trước khi so sánh. Kiểm các trường hợp biên như `null`, danh sách rỗng, phần tử trùng và thay đổi dữ liệu nguồn nếu chúng liên quan đến chức năng.
5. **Kiểm thử trên runtime thực tế:** chạy cùng bộ test trên các phiên bản/JDK dự định hỗ trợ; dùng benchmark riêng cho các yêu cầu hiệu năng. Benchmark đo đặc tính triển khai trong môi trường cụ thể, không tự tạo hợp đồng Java SE.
6. **Kiểm tra phụ thuộc vào API nội bộ nếu cần:** công cụ `jdeps --jdk-internals app.jar` có thể hỗ trợ phát hiện tham chiếu tới JDK internal API trong JAR; việc dùng kết quả công cụ phải gắn với bản JDK mục tiêu.

**Có thể cố ý phụ thuộc triển khai không?** Có, khi ứng dụng thật sự cần một tính năng được **nhà cung cấp JDK hỗ trợ và tài liệu hóa**, hoặc một khả năng vận hành cụ thể. Khi đó phải ghi rõ JDK/phiên bản, cấu hình, rủi ro khi đổi phiên bản và kiểm thử tương ứng. Đó là quyết định kỹ thuật có điều kiện, không phải một cam kết chung của ngôn ngữ Java.

## 7. Các lỗi tư duy thường gặp

| Suy luận sai | Cách hiểu đúng |
| --- | --- |
| “Cùng input chạy năm lần cùng thứ tự, vậy thứ tự được bảo đảm.” | Quan sát lặp lại không thay cho tài liệu cam kết; `HashMap` vẫn không có thứ tự bảo đảm. |
| “`List.copyOf` luôn tạo object mới.” | API bảo đảm hành vi danh sách kết quả; việc tái sử dụng instance có thể xảy ra. |
| “`List.copyOf` làm mọi phần tử bên trong bất biến.” | Không thể sửa cấu trúc `List` qua API; đối tượng phần tử còn có thể thay đổi. |
| “Mọi `Map` đều cho phép `null` vì `HashMap` cho phép.” | Thuộc tính của triển khai cụ thể không tự mở rộng thành cam kết cho mọi `Map`. |
| “API là `public` nên mọi thứ liên quan đến nó đều ổn định.” | Quyền truy cập Java, phạm vi hỗ trợ và hợp đồng tài liệu là ba khái niệm khác nhau. |
| “`Implementation Note` giống `API Specification`.” | Ghi chú triển khai cung cấp thông tin về cách làm; đừng dùng nó thay cam kết API. |
| “Kết quả benchmark là độ phức tạp được ngôn ngữ cam kết.” | Số đo phụ thuộc dữ liệu, JVM và máy; chỉ tin cam kết hiệu năng có điều kiện ghi rõ trong tài liệu. |
| “Đổi JDK làm đổi tên class nội bộ tức là phá tương thích.” | Nếu các hành vi được cam kết vẫn giữ nguyên, thay nội bộ thường không phá hợp đồng. |

## 8. Checklist nhanh khi đọc hoặc viết code Java

Trước khi viết logic phụ thuộc một hành vi, tự hỏi:

- **API nào và ở phiên bản nào** đang đưa ra cam kết? Interface, class cụ thể hay phần mở rộng riêng của JDK?
- Tài liệu có nói **“must/returns/throws”**, hay chỉ nói **“may/typically/implementation note”**?
- Đã xem `null`, thứ tự, ngoại lệ, mutability, thread-safety và những điều kiện áp dụng chưa?
- Mình đang kiểm tra **ngữ nghĩa** hay vô tình kiểm tra tên class nội bộ, thứ tự tình cờ, thông điệp lỗi, thời gian hoặc cách cấp phát?
- Nếu yêu cầu ứng dụng cần một tính chất mạnh hơn, có thể **chọn API bảo đảm tính chất ấy** hoặc thực hiện thao tác tường minh (sort, copy, đồng bộ, truyền charset...) không?
- Test có vẫn hợp lệ khi thay OpenJDK build, đổi cấu hình hoặc nâng phiên bản trong phạm vi hỗ trợ không?

## 9. Tự kiểm tra

**Tình huống A.** Chạy `new HashMap<>(...)` nhiều lần đều ra `{a=1, b=2}`. Có nên so sánh `toString()` với chuỗi này trong test? **Không.** Thứ tự `HashMap` không được bảo đảm. Hãy kiểm tra các cặp khóa–giá trị, hoặc chủ động sort nếu chuỗi có thứ tự là một phần yêu cầu.

**Tình huống B.** `List<String> result = List.copyOf(source)`, sau đó `source.add("X")`. Có thể yêu cầu `result` không thay đổi số phần tử không? **Có**, đối với thay đổi cấu trúc collection nguồn. Nhưng nếu phần tử là object mutable, không được suy ra trạng thái của object ấy đã bị đóng băng.

**Tình huống C.** Ứng dụng cần duyệt theo thứ tự thêm khóa. Dùng `HashMap` vì trong một lần chạy “đúng thứ tự” được không? **Không.** Dùng `LinkedHashMap` với thứ tự chèn hoặc API khác công bố rõ thứ tự cần có.

**Tình huống D.** Một thay đổi JDK làm `List.of("a", "b").getClass().getName()` khác đi nhưng `get(0)` vẫn là `"a"` và danh sách vẫn không thể sửa. Có thể coi riêng việc đổi tên class nội bộ là lỗi API không? **Không.** Tên lớp triển khai của factory không phải lời hứa cần dựa vào.

## Nguồn tham khảo chính thức

- [Java Language Specification và Java Virtual Machine Specification](https://docs.oracle.com/javase/specs/) — chọn phiên bản Java SE cần kiểm tra.
- [`List` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html) — `copyOf`, unmodifiable lists, thứ tự, `null` và Implementation Note.
- [`HashMap` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html) — không cam kết thứ tự duyệt và các điều kiện về hiệu năng.
- [`LinkedHashMap` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html) — thứ tự chèn/duyệt do class công bố.
- [`Collection` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html) — ý nghĩa của unmodifiable và sự khác biệt với bất biến sâu.
- [`List` — Java SE 11 API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/List.html) — đối chiếu API có thể dùng khi dự án yêu cầu tương thích Java 11.

**Ghi nhớ:** Chọn API vì **điều nó cam kết**, kiểm thử theo **hành vi được cam kết**, và chỉ khảo sát nội bộ JDK khi cần giải thích hoặc tối ưu hiệu năng trong một môi trường đã xác định.