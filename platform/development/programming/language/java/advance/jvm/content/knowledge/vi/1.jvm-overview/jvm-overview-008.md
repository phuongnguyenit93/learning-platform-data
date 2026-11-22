# Cách đọc tài liệu theo phiên bản JDK và tách quy tắc khỏi chi tiết triển khai

Khi học JVM, cùng một câu mô tả có thể là **quy tắc bắt buộc của Java**, **hợp đồng của một API**, **khả năng của một phiên bản JDK**, hoặc chỉ là **cách một JVM cụ thể đang cài đặt**. Nhầm bốn loại này dẫn tới kết luận sai khi đổi Java 17 sang 21, nâng JDK của nhà cung cấp khác, hoặc điều chỉnh cờ chạy chương trình. Mục tiêu của bài là tìm đúng tài liệu cho đúng phiên bản và biết chính xác điều gì được bảo đảm.

## 1. Phân biệt lớp tài liệu và đối tượng được mô tả

| Câu hỏi | Nguồn nên đọc trước | Loại kết luận có thể rút ra |
| --- | --- | --- |
| Cú pháp Java, kiểu dữ liệu, overload, class initialization, Java Memory Model? | **JLS** (Java Language Specification) của Java SE tương ứng | Quy tắc ngôn ngữ Java, ví dụ khi nào phép gán hợp lệ và ràng buộc happens-before |
| Bytecode, cấu trúc `.class`, loading/linking, runtime data areas, lệnh JVM? | **JVMS** (Java Virtual Machine Specification) đúng phiên bản | Ràng buộc đối với JVM phù hợp đặc tả, không mặc định áp đặt thuật toán triển khai |
| `HashMap`, `LinkedHashMap`, `Thread`, `String` bảo đảm điều gì? | **Java SE API Specification/Javadoc** đúng phiên bản | Hợp đồng public API, ngoại lệ, tính thứ tự, điều kiện sử dụng |
| `java`, `javac`, `jcmd` có những tùy chọn nào? | **JDK tool guides/man pages** của JDK đang dùng | Cách gọi công cụ và phạm vi hỗ trợ cho phiên bản/phân phối ấy |
| Khi nào xuất hiện một tính năng, được chuẩn hóa hay còn preview? | **Release notes**, tài liệu tính năng và **JEP**, đối chiếu đặc tả cuối cùng | Lịch sử, động cơ, trạng thái thay đổi; JEP không thay thế hợp đồng API/đặc tả đã phát hành |
| HotSpot dùng collector, JIT, layout đối tượng, ngưỡng tối ưu hóa nào? | **Tài liệu VM cụ thể**, option/help, source code và phép đo trên đúng bản build | Hành vi triển khai trong điều kiện xác định; không tự suy rộng sang mọi JVM |

**JDK** là bộ công cụ/phân phối dùng phát triển và chạy ứng dụng; **Java SE** là nền tảng có các đặc tả và API; **JVM** là máy ảo thực thi class files; **HotSpot** là một triển khai JVM. Một JDK thường chứa HotSpot nhưng không được đồng nhất HotSpot với chính JVMS. Nói “JVM luôn dùng C2/G1”, “mọi đối tượng luôn có header 12 byte” là sai về phạm vi cam kết.

Một đoạn trong tài liệu cần được ghi kèm **phiên bản, loại tài liệu và phạm vi phát biểu**. “Java 17” phải làm rõ là Java SE 17 specification, JDK 17 compiler, hay một bản build runtime 17 cụ thể.

## 2. Khóa đúng phiên bản trước khi đọc

Trên máy biên dịch và máy chạy chương trình, kiểm tra độc lập:

```text
java -version
javac -version
java -XshowSettings:properties -version
```

- `java -version`: runtime được PATH hoặc đường dẫn hiện tại chọn; thường hiển thị version, vendor/build và VM.
- `javac -version`: compiler được chọn; có thể thuộc một JDK khác với lệnh `java`.
- Trong kết quả properties, xem `java.version`, `java.vendor`, `java.vm.name`, `java.home`; giá trị thực tế tùy môi trường. Nếu dùng IDE, Gradle, Maven, container hay CI, kiểm tra **JDK thực sự** mà công cụ ấy gọi.
- Ghi thêm hệ điều hành, kiến trúc, vendor, build/patch và các VM flags nếu đang đối chiếu hành vi hiệu năng hoặc GC.

Các con số cần phân biệt:

1. **Phiên bản ngôn ngữ**: cú pháp mà compiler chấp nhận, ví dụ Java 17.
2. **Phiên bản public API**: phương thức/lớp được phép gọi trên nền tảng đích.
3. **Phiên bản class file**: định dạng bytecode mà JVM có thể nạp.
4. **Phiên bản runtime thực tế**: JVM và thư viện chạy production.

Ví dụ class-file major tương ứng: Java 8 → 52, Java 11 → 55, Java 17 → 61, Java 21 → 65, Java 25 → 69, Java 27 → 71. Đây là phiên bản định dạng class file được giới thiệu, **không phải** chứng cứ chắc chắn file được tạo bằng JDK nào: compiler JDK mới có thể phát sinh bytecode cho đích cũ.

Khi biên dịch cho runtime Java 17 bằng một `javac` có hỗ trợ release 17, thường dùng:

```bash
javac --release 17 ReadContracts.java
javap -verbose ReadContracts
java ReadContracts
```

Trong `javap -verbose`, tìm dòng `major version: 61`. Tùy chọn `--release 17` giới hạn phiên bản ngôn ngữ, định dạng class file **và API nền tảng được tài liệu hóa** mà compiler cho phép sử dụng. Chỉ đặt `-source 17 -target 17` chưa đủ để bảo đảm bạn không vô tình tham chiếu API chỉ có trên JDK mới. `--release` cũng không chứng minh mọi thư viện ngoài, native library và hành vi môi trường đều tương thích Java 17; cần build/test với runtime đích.

Để chạy class file cần hỗ trợ major/minor tương ứng. Lỗi `UnsupportedClassVersionError` thường báo runtime không đọc được phiên bản class file; trước khi kết luận, xem dòng major, runtime thực dùng và khả năng dự án có sử dụng **preview feature** (class file preview có quy tắc riêng, có thể đòi hỏi `--enable-preview` và đúng release).

## 3. Tìm tài liệu theo một “đường đi” có thể kiểm chứng

**Bước 1 — Xác định câu hỏi thuộc lớp nào.** Ví dụ: “JVM có bắt buộc lưu object trên heap?” liên quan JVMS/JLS; “GC nào mặc định?” liên quan VM options của build; “`Map` có thứ tự duyệt ổn định?” phải đọc hợp đồng API của implementation `Map` cụ thể.

**Bước 2 — Chọn edition, không chỉ chọn kết quả tìm kiếm đầu tiên.** Trang đặc tả thường có `se17`, `se21`, `se27`; Javadoc/man pages thường nằm dưới `/en/java/javase/17/`, `/21/`, v.v. Không ghép một trích dẫn JLS 17 với một đoạn API 27 rồi coi là cùng hợp đồng. Khi bài toán liên quan *hai* runtime, mở **cả hai** bản tài liệu và so các điều khoản tương ứng.

**Bước 3 — Đọc phần quy định nguyên văn trong ngữ cảnh.** Kiểm tra heading, precondition, ngoại lệ, “must/shall”, “may”, “typically”, “implementation note”, “since”, “deprecated”, “preview”, “unspecified”, “implementation-specific”. Đừng biến các từ “thường”, “có thể”, “ví dụ” thành “luôn”, “bắt buộc”. Ví dụ code trong tài liệu giúp hiểu quy tắc nhưng không nhất thiết mô tả mọi trường hợp.

**Bước 4 — Đối chiếu việc thay đổi phiên bản.** Từ yêu cầu thiết kế hoặc tài liệu feature đi tới đặc tả/Javadoc cuối cùng của chính release đó; dùng release notes để xác định sửa đổi, loại bỏ hoặc thay đổi mặc định. Nếu có JEP, kiểm tra trạng thái và release mục tiêu, đặc biệt với preview/incubator.

**Bước 5 — Kiểm chứng hành vi thực tế khi câu hỏi nói về hiệu năng.** Ghi JVM vendor/build và cờ khởi động, tái hiện benchmark/profile trên đúng máy. Một lần quan sát không thể “nâng” chi tiết HotSpot thành quy tắc Java.

### Độ mạnh của chứng cứ

Có thể diễn đạt kết luận theo mẫu: “**Theo [tài liệu + edition + mục], trong điều kiện [điều kiện], hành vi [X] được bảo đảm/không được bảo đảm; quan sát [Y] là của [runtime/build]**”.

| Dấu hiệu trong tài liệu | Cách diễn giải an toàn |
| --- | --- |
| Quy định của JLS/JVMS hoặc yêu cầu bắt buộc trong API | Điều mọi implementation phù hợp phạm vi ấy phải đáp ứng |
| Javadoc mô tả order/exception/case cụ thể | Hợp đồng cho class/method và điều kiện đã ghi; không suy rộng sang class khác |
| `Implementation Note` hoặc “in this implementation” | Thông tin cách cài đặt hiện tại, có thể đổi khi đổi JDK/build |
| “Typically”, “usually”, “may” | Mô tả trường hợp thường gặp/khả năng; không phải bảo đảm mọi lần |
| “No guarantee”, “unspecified” | Chương trình **không được phụ thuộc** vào giá trị/thứ tự đó, dù quan sát thấy nó lặp lại |
| JEP, bug ticket, bài blog, benchmark | Giải thích lịch sử hoặc quan sát; đối chiếu tài liệu chuẩn và phiên bản phát hành |

“Unspecified” không đồng nghĩa lỗi ngẫu nhiên: implementation có thể cho cùng kết quả rất lâu, nhưng hợp đồng công khai không hứa hẹn kết quả ấy. Ngược lại, “implementation-dependent” không cho phép ta tùy ý nói mọi hành vi đều đúng; implementation vẫn phải đáp ứng các ràng buộc bắt buộc khác.

## 4. Ví dụ 1 — Một kết quả đúng ở máy tôi chưa phải hợp đồng API

Javadoc Java 17 của `HashMap` nói rõ **không bảo đảm** thứ tự các phần tử và không hứa thứ tự giữ nguyên theo thời gian. Javadoc `LinkedHashMap` mô tả thứ tự duyệt có thể dự đoán được; với constructor mặc định, đó là thứ tự chèn khóa.

Tạo file **`ReadContracts.java`**:

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class ReadContracts {
    public static void main(String[] args) {
        Map<String, Integer> ordered = new LinkedHashMap<>();
        ordered.put("beta", 2);
        ordered.put("alpha", 1);
        System.out.println(ordered.keySet());

        Map<String, Integer> unordered = new HashMap<>();
        unordered.put("beta", 2);
        unordered.put("alpha", 1);
        System.out.println(unordered.containsKey("alpha"));
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên có hỗ trợ `--release 17`:

```bash
javac --release 17 ReadContracts.java
java ReadContracts
```

**Stdout**:

```text
[beta, alpha]
true
```

- Dòng đầu ổn định theo hợp đồng của `LinkedHashMap` dùng chế độ insertion-order. Nếu chọn constructor `accessOrder=true`, quy tắc thứ tự khác đi; luôn đọc đúng constructor.
- Dòng hai chỉ hỏi `HashMap` có chứa khóa hay không. Đừng lấy thứ tự `unordered.keySet()` in được trên một máy để viết test hoặc business logic.
- Class file được tạo bằng `--release 17` có major 61; nguồn code chạy đúng trên một JDK 27 không có nghĩa hợp đồng này đã được đọc từ “Javadoc 27”. Điều đang chứng minh ở đây dựa vào API Java 17.

Cách sửa code phụ thuộc sai hợp đồng: nếu giao diện/JSON/report cần thứ tự chèn, chọn cấu trúc có bảo đảm thứ tự và viết test theo hợp đồng; nếu chỉ cần tra cứu khóa, không ràng buộc test vào thứ tự `HashMap`.

## 5. Ví dụ 2 — Phân biệt vùng nhớ chuẩn với cách HotSpot lưu trữ

JVMS mô tả các **run-time data areas** như heap, Java Virtual Machine stacks, method area, run-time constant pool và các ràng buộc liên quan. Đặc tả nói rõ JVM có quyền chọn nhiều cách tổ chức lưu trữ để đáp ứng yêu cầu quan sát được.

Hãy tách hai phát biểu:

- **Mức đặc tả:** JVM cung cấp heap là vùng bộ nhớ dùng chung giữa các thread để cấp phát class instances và arrays; vùng đó được quản lý tự động, và JVM không bắt buộc chọn một thuật toán thu gom rác cụ thể.
- **Mức triển khai:** trên một bản HotSpot, đối tượng có object header kích thước nhất định, JVM dùng compressed references hay collector cụ thể, hoặc JIT biên dịch phương thức sau một số lần gọi. Đây là các lựa chọn gắn với build/cấu hình/kiến trúc.

Vì thế, từ sơ đồ heap trong JVMS **không suy ra** mọi object có số byte giống nhau, có địa chỉ quan sát được ổn định, phải dùng G1, phải JIT, hoặc được biểu diễn bằng một layout cố định. Nếu câu hỏi là “Tại sao ứng dụng chiếm X MB?”, dùng profiler/GC logs/tài liệu HotSpot và cấu hình cụ thể, không chỉ dẫn định nghĩa heap từ đặc tả.

Tương tự, từ việc một GC là **mặc định** ở một JDK không suy ra chuẩn Java bắt buộc JVM khác chọn GC ấy. Các mặc định và cờ VM có thể thay đổi theo phiên bản, nền tảng hoặc nhà cung cấp.

## 6. Ví dụ 3 — Phân biệt xuất hiện tính năng và khả năng dùng trên runtime đích

Giả sử nhóm phát triển muốn dùng virtual threads. Hãy hỏi tuần tự:

1. Trong release nào tính năng là chính thức, hay còn preview? Đọc lịch sử JEP, rồi xác nhận API trong Javadoc của release mục tiêu.
2. Compiler, build tool và runtime production có cùng mức release không?
3. Code dùng API ấy có qua `javac --release <phiên-bản-production>` không? Ví dụ API virtual threads phổ biến được chuẩn hóa ở Java 21; mã dùng `Thread.ofVirtual()` không nằm trong Java SE 17 API.
4. Ràng buộc hành vi nào là public API, và điều nào chỉ là scheduling, pinning hay lựa chọn hiện tại của một VM? Đọc tài liệu tương ứng thay vì dự đoán từ một ảnh chụp thread dump.

Đừng hiểu JEP như một hợp đồng bất biến kể từ lúc đề xuất: tính năng có thể đi qua các vòng preview rồi thay đổi trước khi thành chính thức. Nếu ứng dụng chỉ hỗ trợ Java 17, việc máy developer cài JDK 21/27 không tự mở rộng API của production.

## 7. Tách “chạy được” khỏi “được bảo đảm” khi nâng JDK

Các tương thích cần xem **riêng**, tránh gom thành một câu “Java tương thích ngược”:

| Khía cạnh | Câu hỏi kiểm tra | Bằng chứng cần lấy |
| --- | --- | --- |
| Source compatibility | Mã nguồn cũ có còn biên dịch? Từ khóa/ngôn ngữ/preview thay đổi không? | JLS và tài liệu `javac` của release đích |
| Binary compatibility | Class file cũ có nạp và liên kết được? API signature có thay đổi? | JVMS class-file/loading và JLS binary compatibility, release notes |
| API compatibility | Method/class/module công khai đang dùng còn hiện diện, có thay đổi hợp đồng? | Javadoc đúng version, `@since`, deprecation/removal notes |
| Runtime behavior | Chương trình còn đúng trước khác biệt về thứ tự không được bảo đảm, timing, GC, locale...? | Đặc tả + test trên runtime đích |
| Operational compatibility | Cờ JVM, logging, monitoring, container limits, vendor/build có khác? | Man pages, VM guide và kiểm thử vận hành |

Có thể chạy ổn trên nhiều phiên bản là **bằng chứng thực nghiệm có ích** nhưng yếu hơn một bảo đảm được tài liệu hóa. Ngược lại, nếu một tình huống phụ thuộc vào chi tiết không được bảo đảm, chương trình vẫn có thể “pass” nhiều năm trước khi hỏng do thay JDK hoặc khối lượng dữ liệu.

## 8. Cách ghi chú kiến thức JVM có thể kiểm toán

Với mỗi phát biểu kỹ thuật, lưu một dòng có thể truy ngược:

```text
Claim: LinkedHashMap mặc định duyệt theo thứ tự chèn.
Scope: Java SE 17 API; java.util.LinkedHashMap; constructor mặc định.
Source: Javadoc Java SE 17, phần mô tả class và constructor.
Guarantee: Thứ tự chèn cho trường hợp này; không suy ra HashMap có cùng thứ tự.
Verification: ReadContracts.java trên JDK 17 và runtime đích.
Implementation detail: Cấu trúc linked list được mô tả, nhưng không cần
                     phụ thuộc trực tiếp vào node layout hay kích thước byte.
```

Đối với một claim như “HotSpot bản X, kiến trúc Y, bật Z dùng object header N byte”, ghi rõ lệnh nhận diện VM, build, cấu hình và công cụ đo; không chuyển nó thành câu “JVM object luôn N byte”. Khi tài liệu các phiên bản khác nhau, trình bày **trước/sau** và dẫn từng bản. Nếu chưa có nguồn bảo đảm, đánh dấu đó là quan sát hoặc giả thuyết cần xác nhận.

## 9. Những lỗi đọc tài liệu hay gặp

- **Nhầm “JVM” với “HotSpot”:** lấy tài liệu GC/JIT của HotSpot làm luật JVMS.
- **Nhầm JDK đang cài với nền tảng hỗ trợ:** máy build mới hơn máy production; thiếu `--release` và CI chạy trên runtime đích.
- **Dùng Javadoc sai version:** dựa vào API mới khi ứng dụng vẫn chạy Java cũ, hoặc áp đặt chi tiết Java cũ cho phiên bản mới.
- **Biến ví dụ thành quy tắc:** suy từ một output, bytecode compiler cụ thể, ảnh profiler hoặc một benchmark rằng mọi JVM phải giống như vậy.
- **Bỏ điều kiện của hợp đồng:** `LinkedHashMap` insertion-order khác access-order; cấu hình, đồng thời, mutability, null và ngoại lệ có thể đổi ý nghĩa của kết luận.
- **Đọc tiêu đề JEP mà không xem status:** nhầm proposed/preview/incubator với tính năng chính thức của release đang dùng.
- **Trộn “thực hiện được” với “ổn định lâu dài”:** relying on internal APIs, undocumented `-XX` flags, timing và memory layout có thể gây lỗi khi nâng cấp.

## 10. Checklist cho một phát biểu về Java/JVM

1. Tôi đã xác định **JDK/compiler/runtime version, vendor, build** thật sự chưa?
2. Câu hỏi nói về **ngôn ngữ, class-file/JVM, API, công cụ hay VM implementation**?
3. Tôi đang xem **edition nào**, và điều khoản nào quy định hành vi ấy?
4. Câu tôi trích là **must/guaranteed** hay chỉ “may/typically/implementation note”?
5. Có giới hạn nào về constructor, option, OS, kiến trúc, concurrency hoặc preview không?
6. Nếu nâng từ release A sang B, tôi đã đối chiếu **cả hai** tài liệu và test trên B chưa?
7. Tôi có đang dùng kết quả quan sát riêng như một bảo đảm chung không?

Nếu trả lời rõ bảy câu này, bạn sẽ phân biệt được **quy tắc có thể dựa vào khi viết code** và **đặc điểm cần đo/kiểm tra lại khi thay JVM**.

## Tài liệu gốc để tra cứu theo phiên bản

- [Java SE Language và JVM Specifications — danh mục các edition](https://docs.oracle.com/javase/specs/): chọn edition theo Java SE đang nghiên cứu.
- [JLS Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/): quy tắc ngôn ngữ, chương về threads/memory model và binary compatibility.
- [JVMS Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/): cấu trúc JVM, class file, loading/linking, các runtime data areas.
- [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html): đọc contract của từng class/method; đối chiếu trực tiếp [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) với [LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).
- [Tài liệu lệnh javac của Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-source`, `-target`.
- [Danh mục JEP của OpenJDK](https://openjdk.org/jeps/0): lịch sử và tình trạng đề xuất; luôn đối chiếu đặc tả/API ở release phát hành.

**Nguyên tắc đọc:** trích đúng nguồn, đúng edition, đúng điều kiện, rồi mới quyết định có thể phụ thuộc vào hành vi ấy hay chỉ nên coi nó là chi tiết của một triển khai.
