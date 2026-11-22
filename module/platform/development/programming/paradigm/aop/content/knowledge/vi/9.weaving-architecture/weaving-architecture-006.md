# Quan hệ giữa thứ tự xây dựng và kết quả dệt trong kiến trúc AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **weaving (dệt)** là quá trình kết hợp hành vi cắt ngang (**advice**) với những vị trí thực thi (**join point**) mà **pointcut** lựa chọn. Một chương trình có thể trải qua nhiều công đoạn: phân tích nguồn, biên dịch, tạo mã, biến đổi bytecode, liên kết thành phần, nạp lớp hoặc tạo lớp bọc lúc chạy. **Thứ tự thực hiện các công đoạn và các phép biến đổi có thể ảnh hưởng trực tiếp tới mã cuối cùng, tập điểm được chọn và hành vi thực thi.**

Tuy nhiên, **“thứ tự xây dựng” không tự động bằng “thứ tự advice chạy”**. Một công cụ có thể xây dựng nhiều aspect theo thứ tự bất kỳ nhưng sử dụng quy tắc precedence rõ ràng để tạo cùng một chuỗi advice. Ngược lại, một hệ thống ghép các lớp wrapper tuần tự có thể tạo **thứ tự bao ngoài–bên trong ngược với thứ tự thêm wrapper**. Cần phân biệt các tầng này trước khi kết luận một thay đổi thứ tự build làm chương trình chạy khác.

Bài này trình bày mối quan hệ giữa **pipeline xây dựng**, **weaving**, **ưu tiên advice**, **tính ổn định của kết quả dệt**, tác động khi có nhiều phép biến đổi và cách kiểm thử. Những mô hình và giả mã được dùng để giải thích kiến trúc AOP nói chung; thời điểm, cú pháp và ngữ nghĩa cụ thể tùy cơ chế triển khai.

## 1. Bốn loại “thứ tự” phải tách riêng

Cụm từ “thứ tự” trong AOP có thể chỉ các khái niệm khác nhau:

| Thứ tự | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Thứ tự xây dựng (build order)** | Module, nguồn, lớp hay bước build nào được xử lý trước? | Tạo mã → biên dịch → xử lý bytecode → đóng gói |
| **Thứ tự áp dụng phép biến đổi (transformation/weaving order)** | Phép biến đổi nào đọc/sửa biểu diễn chương trình trước? | `W1` xử lý class trước `W2` |
| **Thứ tự kết hợp advice (precedence/composition)** | Advice nào bao ngoài/được ưu tiên ở một join point? | `Audit(Timing(Business))` |
| **Thứ tự chạy (runtime execution order)** | Khi thực thi, before/after/around được quan sát theo thứ tự gì? | `Audit.before` → `Timing.before` → business |

Bốn thứ tự này **có thể tác động lẫn nhau**, nhưng không được dùng thay thế cho nhau.

Ví dụ, một hệ thống build biên dịch hai tệp chứa aspect theo thứ tự A rồi B. Nếu bộ weaver dùng một khai báo ưu tiên **B bao ngoài A**, thứ tự thực thi vẫn là `B.before → A.before → nghiệp vụ → A.after → B.after`. Thứ tự tên tệp hoặc thời điểm biên dịch **không phải** bằng chứng rằng A có precedence cao hơn B.

Ngược lại, nếu một chương trình xây dựng chuỗi xử lý bằng cách lần lượt bọc A rồi bọc B:

~~~text
initial = Business
after A = A(Business)
after B = B(A(Business))
~~~

thì B là **lớp ngoài** và thường chạy phần trước trước A. Đây là kết quả của **toán tử bọc được chọn**, không phải định luật chung về tất cả weaver AOP.

## 2. Weaving xảy ra ở những giai đoạn nào?

Một kiến trúc AOP có thể lựa chọn những thời điểm kết hợp hành vi khác nhau.

### 2.1 Dệt trước hoặc trong quá trình biên dịch

Với cách xử lý mã nguồn hoặc một compiler có khả năng nhận biết aspect, công cụ có thể phân tích khai báo điểm cắt, kiểu và cấu trúc chương trình rồi tạo mã kết hợp. Một số thông tin nguồn có thể hỗ trợ so khớp và kiểm tra lỗi trước khi chạy.

Sơ đồ khái niệm:

~~~text
Mã nghiệp vụ + khai báo aspect
              |
              v
     Phân tích/chọn join point
              |
              v
       Kết hợp hành vi
              |
              v
      Mã/bytecode kết quả
~~~

Không nên mặc định mọi công cụ dệt từ mã nguồn có thể nhìn thấy các phần tử được sinh ở **bước chạy sau**, chẳng hạn lớp proxy tạo tại runtime. Tập mã và metadata có sẵn **ở thời điểm dệt** quyết định những gì công cụ có thể phân tích.

### 2.2 Dệt sau biên dịch, trên bytecode

Một weaver có thể đọc các tệp lớp đã được compiler tạo và biến đổi chúng:

~~~text
Java sources
     |
     v
Compiled classes
     |
     +---> Bytecode weaver + aspect definitions
                    |
                    v
              Woven classes
                    |
                    v
              Packaging
~~~

Ở tầng này, các chữ ký đã qua **type erasure**, bridge/synthetic methods và mã sinh có thể đã tồn tại. Một pointcut theo chữ ký ở bytecode có thể cần hiểu cấu trúc khác với cú pháp generic ở mã nguồn; một bộ AOP cũng có thể **chủ động loại bỏ** một số phương thức do compiler sinh khỏi tập join point được hỗ trợ.

Nếu công cụ biến đổi khác cũng chèn mã hoặc sửa descriptor trong cùng pipeline, **thứ tự các phép biến đổi có thể làm chúng nhìn thấy những biểu diễn khác nhau**.

### 2.3 Dệt khi nạp lớp

Với mô hình load-time weaving, một bộ biến đổi có thể thay đổi biểu diễn lớp khi runtime chuẩn bị nạp nó. Khi đó **thứ tự tác nhân biến đổi**, điều kiện lớp đã được nạp hay chưa, class loader nào chịu trách nhiệm và cấu hình runtime trở nên quan trọng.

Lớp đã được nạp trước khi cấu hình can thiệp có hiệu lực có thể không đi qua cùng đường biến đổi. Không nên suy rằng chỉ đổi file build là đủ để ảnh hưởng mọi lớp đã nạp trong một JVM đang chạy.

### 2.4 Lớp bọc hoặc proxy tại runtime

Một cơ chế AOP có thể tạo một wrapper/proxy chặn lời gọi qua một giao diện hoặc biên đối tượng:

~~~text
Caller → Outer proxy → Inner proxy → Target object
~~~

Ở đây, thứ tự tạo lớp bọc và quy tắc ghép của container/builder có thể xác định proxy nào ở ngoài. Nhưng proxy thường chỉ quan sát lời gọi **đi qua nó**; gọi trực tiếp vào target hoặc một lời gọi nội bộ bỏ qua proxy có thể không được advice tương ứng can thiệp.

**Tóm lại:** thời điểm weaving ảnh hưởng đến **tập join point có thể quan sát**, thông tin cấu trúc sẵn có và tính chất của artifact tạo ra. Thời điểm đó không tự cung cấp quy tắc ưu tiên chung giữa nhiều advice.

## 3. “Kết quả dệt” là gì?

Kết quả weaving không chỉ là “trong bytecode có thêm vài dòng ghi log”. Nó gồm ít nhất ba lớp quan sát:

1. **Artifact được tạo:** mã nguồn trung gian, bytecode, class đã nạp, proxy, wrapper hoặc metadata do weaver sinh.
2. **Cấu trúc can thiệp:** những join point được chọn, thứ tự kết hợp advice, đường gọi tiếp tục hoặc short-circuit.
3. **Hành vi runtime:** giá trị trả về, ngoại lệ, tác dụng phụ, thứ tự ghi log, thời gian đo, kiểm soát quyền và trạng thái tài nguyên.

Hai lần build có thể cho **bytecode khác nhau** vì timestamp, đường dẫn nguồn, tên synthetic hoặc metadata nhưng **hành vi tương đương** đối với các yêu cầu cần kiểm tra. Ngược lại, hai artifact cùng được biên dịch thành công vẫn có thể khác thứ tự advice và gây sai nghĩa vụ bảo mật hoặc giao dịch.

Cần định nghĩa rõ tiêu chuẩn so sánh:

- **Byte-for-byte reproducibility:** kết quả artifact trùng từng byte theo mô hình build có kiểm soát.
- **Structural equivalence:** tập join point, chuỗi advice và loại biến đổi tương đương.
- **Behavioral equivalence:** các quan sát mà hợp đồng nghiệp vụ cho phép vẫn giống nhau.

Không nên khẳng định mọi build đúng bắt buộc có bytecode giống hệt nhau; nhưng **thay đổi cấu trúc hoặc kết quả chạy không mong muốn** phải được nhận diện.

## 4. Vì sao các phép biến đổi không nhất thiết giao hoán?

Gọi `P` là biểu diễn chương trình, `W_A` và `W_B` là hai phép biến đổi. Theo toán học, hai thứ tự:

~~~text
Result1 = W_B(W_A(P))
Result2 = W_A(W_B(P))
~~~

**không nhất thiết tạo cùng kết quả**:

~~~text
W_B(W_A(P)) ≠ W_A(W_B(P))
~~~

Dấu khác nhau ở đây là một **khả năng**, không phải kết luận mọi cặp weaver đều khác nhau. Nếu hai phép biến đổi độc lập và công cụ định nghĩa cơ chế kết hợp ổn định, chúng có thể cho kết quả tương đương.

### 4.1 Tương tác chọn điểm

Giả sử `W_A` tạo thêm một phương thức `helper()` và `W_B` chọn mọi method execution trong một phạm vi. Nếu `W_B` chạy sau `W_A`, nó **có thể** thấy helper mới; nếu chạy trước, helper chưa tồn tại. Khả năng có thật join point cho helper, và việc mã sinh có được chọn hay không, vẫn tùy bộ weaver.

Trường hợp ngược lại, nếu `W_A` xóa, đổi tên, inlining hoặc biến đổi descriptor mà `W_B` dựa vào để match, `W_B` có thể chọn tập điểm khác.

### 4.2 Tương tác hành vi

Ví dụ `W_A` thêm validation, `W_B` thêm cache:

~~~text
Validation(Cache(Business))
Cache(Validation(Business))
~~~

Ở cấu trúc đầu, kiểm tra validation ở ngoài sẽ chạy trước nhánh cache. Ở cấu trúc sau, một cache hit có thể trả sớm và **bỏ qua validation bên trong**. Nếu validation là kiểm tra quyền bắt buộc thì thứ tự thứ hai có thể không chấp nhận được.

Ví dụ này minh họa **thứ tự kết hợp advice có thể ảnh hưởng hợp đồng**, không hàm ý thứ tự mà một công cụ AOP cụ thể tự động chọn.

### 4.3 Tương tác đo lường

~~~text
Timing(Transaction(Business))
Transaction(Timing(Business))
~~~

Nếu timing nằm ngoài transaction, nó có thể bao gồm thời gian tạo và kết thúc giao dịch. Nếu timing bên trong transaction, độ trễ đo được hẹp hơn. Cả hai số đo có thể hợp lệ **nếu tên metric nói đúng phạm vi**; không nên gọi cả hai là “thời gian nghiệp vụ thuần túy”.

### 4.4 Tương tác ngoại lệ

Một advice A bắt lỗi rồi trả fallback, trong khi advice B dựa vào ngoại lệ để rollback. Nếu A nằm **trong B**, B có thể thấy lần gọi trả về bình thường; nếu A nằm **ngoài B**, B có thể nhận lỗi và rollback trước khi A trả fallback. Hai kết quả rất khác nhau dù advice và pointcut không đổi.

Vì vậy, quyết định precedence cần bắt nguồn từ **hợp đồng nghiệp vụ**, không chỉ từ độ đẹp của thứ tự log.

## 5. Thứ tự “áp dụng” wrapper có thể đảo ngược “thứ tự chạy”

Đây là một nguồn lỗi đặc biệt thường gặp với builder tự tạo chuỗi xử lý.

Nếu thuật toán là:

~~~text
chain = Business
for each advice in constructionList:
    chain = Wrap(advice, chain)
~~~

mỗi lần `Wrap` bao **ngoài** chuỗi hiện có. Do đó:

~~~text
constructionList = [AUDIT, TIMING]

step 0: Business
step 1: AUDIT(Business)
step 2: TIMING(AUDIT(Business))
~~~

**Thứ tự thêm:** `AUDIT` rồi `TIMING`.

**Thứ tự chạy before:** `TIMING` rồi `AUDIT`, sau đó mới tới `Business`.

**Thứ tự chạy after:** `AUDIT` rồi `TIMING` nếu cả hai lớp cho phép đi tiếp và trả về bình thường.

Đây là hệ quả của việc dùng phép bọc **bên ngoài** qua vòng lặp. Một builder khác có thể dùng `foldRight`, đảo danh sách trước khi áp dụng, hoặc đặt vị trí thêm mới **bên trong** chuỗi. Vì thế không có công thức chung rằng “phần tử đầu tiên trong danh sách luôn là outermost”.

## 6. Ví dụ Java 17 chạy độc lập: thứ tự xây dựng và đầu ra

Ví dụ sau dùng **wrapper Java thuần túy** để diễn giải cấu trúc kết hợp advice. Nó không khai báo ngôn ngữ pointcut hoặc tự dệt bytecode, mà cố ý đặt tên `assemble` và `wrap` để cho thấy chính xác **quy tắc xây dựng nào tạo thứ tự chạy nào**.

Chương trình có hai lớp minh họa `AUDIT` và `TIMING`, một nghiệp vụ `Business`, nhánh thành công và nhánh ném ngoại lệ. Mỗi wrapper thêm tên của mình vào kết quả, giúp thấy rằng **thứ tự lồng nhau có thể đổi cả giá trị trả về**, không chỉ thứ tự các dòng log.

Lưu file `WeavingBuildOrderDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;

public class WeavingBuildOrderDemo {
    @FunctionalInterface
    interface Step {
        String run(String input);
    }

    static Step business() {
        return input -> {
            System.out.println("BUSINESS " + input);
            if ("fail".equals(input)) {
                throw new IllegalStateException("refused");
            }
            return input.toUpperCase(Locale.ROOT);
        };
    }

    static Step wrap(String name, Step next) {
        return input -> {
            System.out.println(name + " BEFORE");
            try {
                String innerResult = next.run(input);
                String result = name + "(" + innerResult + ")";
                System.out.println(name + " AFTER " + result);
                return result;
            } catch (RuntimeException error) {
                System.out.println(name + " ERROR "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println(name + " FINALLY");
            }
        };
    }

    // Chú ý: mỗi lần lặp tạo wrapper bên NGOÀI chuỗi đang có.
    static Step assemble(List<String> constructionOrder) {
        Step chain = business();
        for (String name : constructionOrder) {
            chain = wrap(name, chain);
        }
        return chain;
    }

    static void demonstrate(
            String caseName, List<String> order, String input) {
        System.out.println("CASE " + caseName);
        Step chain = assemble(order);
        try {
            System.out.println("RESULT " + chain.run(input));
        } catch (RuntimeException error) {
            System.out.println("CALLER " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        demonstrate(
                "AUDIT_THEN_TIMING",
                List.of("AUDIT", "TIMING"),
                "ok");
        demonstrate(
                "TIMING_THEN_AUDIT",
                List.of("TIMING", "AUDIT"),
                "ok");
        demonstrate(
                "FAIL",
                List.of("AUDIT", "TIMING"),
                "fail");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac WeavingBuildOrderDemo.java
java WeavingBuildOrderDemo
~~~

Stdout chính xác của chương trình:

~~~text
CASE AUDIT_THEN_TIMING
TIMING BEFORE
AUDIT BEFORE
BUSINESS ok
AUDIT AFTER AUDIT(OK)
AUDIT FINALLY
TIMING AFTER TIMING(AUDIT(OK))
TIMING FINALLY
RESULT TIMING(AUDIT(OK))
CASE TIMING_THEN_AUDIT
AUDIT BEFORE
TIMING BEFORE
BUSINESS ok
TIMING AFTER TIMING(OK)
TIMING FINALLY
AUDIT AFTER AUDIT(TIMING(OK))
AUDIT FINALLY
RESULT AUDIT(TIMING(OK))
CASE FAIL
TIMING BEFORE
AUDIT BEFORE
BUSINESS fail
AUDIT ERROR IllegalStateException
AUDIT FINALLY
TIMING ERROR IllegalStateException
TIMING FINALLY
CALLER refused
~~~

### 6.1 Phân tích hai thứ tự xây dựng

Trường hợp đầu:

~~~text
assembly: AUDIT → TIMING
result:   TIMING(AUDIT(Business))
~~~

Thế nên `TIMING BEFORE` xuất hiện trước `AUDIT BEFORE`; lớp `AUDIT` hoàn tất trước và `TIMING` hoàn tất sau.

Trường hợp thứ hai:

~~~text
assembly: TIMING → AUDIT
result:   AUDIT(TIMING(Business))
~~~

Cùng hai wrapper và cùng input `"ok"` nhưng kết quả lần lượt là:

~~~text
TIMING(AUDIT(OK))
AUDIT(TIMING(OK))
~~~

Tức các phép kết hợp **không giao hoán** đối với ví dụ này. Điều đó cho thấy chỉ cần thay thứ tự ghép có thể đổi kết quả quan sát được.

### 6.2 Phân tích nhánh lỗi

Ở trường hợp `FAIL`, thân nghiệp vụ ném `IllegalStateException`. Wrapper trong `AUDIT` quan sát lỗi trước, chạy `finally`, rồi lớp ngoài `TIMING` quan sát lỗi và chạy `finally`. Không có dòng `AFTER` thành công bởi phương thức bên trong không trả về bình thường.

Ví dụ giữ nguyên ngoại lệ gốc. Trong AOP thực tế, nếu một around advice bắt rồi **nuốt hoặc biến đổi ngoại lệ**, lớp ngoài có thể nhìn thấy một kết quả hoặc kiểu lỗi khác. Vì thế cần kiểm thử đường lỗi theo **thứ tự lồng nhau thật**, không chỉ đoán từ tên advice.

### 6.3 Giới hạn của ví dụ

- `AUDIT` và `TIMING` chỉ là tên wrapper. Chương trình không tạo audit store và không đo thời gian thật.
- Việc thêm tên vào giá trị trả về có chủ đích để minh họa sự **khác nhau của kết quả**; một advice đo lường production thường phải **bảo toàn kết quả gốc**.
- Đây là **mô hình ghép lúc chạy**. Không thể suy rằng một weaver compile-time cũng bọc các lớp theo đúng vòng lặp này.
- Chương trình không đăng ký pointcut và chỉ bao lời gọi qua chuỗi `Step` do `assemble` tạo. Không áp dụng kết quả này cho mọi method-call/execution join point.

## 7. Build order, weaving order và advice precedence phải được cấu hình độc lập

Một hệ thống AOP có thể có cơ chế **thứ tự ưu tiên (precedence)** ở cấp aspect hoặc advice. Nếu có, cơ chế đó thường dùng để giải quyết nhiều advice cùng khớp một join point. Nhưng cần xác minh:

1. Precedence áp dụng cho **các aspect khác nhau** hay cả advice trong **cùng một aspect**?
2. Một thứ tự ưu tiên cao hơn nghĩa là **bao ngoài**, chạy **before sớm hơn**, hay quy tắc khác?
3. Khi một advice `before` và một advice `after` cùng khớp, quan hệ precedence được định nghĩa thế nào?
4. Có hỗ trợ **around** với khả năng `proceed` không? Nếu có, advice ngoài có thể chặn advice trong.
5. Trường hợp ưu tiên đồng hạng hay chưa khai báo có **thứ tự bảo đảm** không?
6. Nền tảng có coi một danh sách cấu hình là order of **construction** hay order of **execution** không?

Không mặc định:
- Tệp aspect xuất hiện trước trong thư mục sẽ chạy trước.
- Compiler đọc class A trước class B thì A có precedence cao hơn.
- Thứ tự classpath, tên alphabet hoặc thứ tự Reflection là hợp đồng ưu tiên.
- Giá trị priority số nhỏ luôn chạy trước; quy ước số phải đọc theo nền tảng.
- Một `after` luôn dùng cùng thứ tự như `before`.

### 7.1 Trong mô hình lồng nhau, đường vào và đường ra trái chiều

Nếu đã xác lập rõ cấu trúc:

~~~text
A(B(C(Business)))
~~~

thì đường vào trước khi gọi tiếp thường là:

~~~text
A.before → B.before → C.before → Business
~~~

khi kết thúc bình thường:

~~~text
Business → C.after → B.after → A.after
~~~

Đây là hệ quả ngăn xếp của **around wrappers**, không phải tuyên bố mọi loại advice `after` độc lập sẽ luôn có đúng thứ tự đó trong mọi cơ chế.

### 7.2 Thứ tự có thể chỉ là quan hệ bộ phận

Những bất biến quan trọng như `Security` phải chạy trước tác dụng phụ, hoặc `Transaction` cần bao một đoạn nhất định, có thể được diễn tả bằng **quan hệ ưu tiên bắt buộc**. Không phải lúc nào cũng cần sắp xếp tuyến tính mọi aspect.

Ví dụ:

~~~text
Security outside BusinessEffects
Timing may be outside or inside Audit (depending on desired metric)
~~~

Nếu nền tảng không cho xác định một quan hệ cần thiết, không nên dựa vào thứ tự ngẫu nhiên; thay vào đó có thể hợp nhất các bước phụ thuộc chặt vào một advice hoặc ranh giới nghiệp vụ đáng tin.

## 8. Thứ tự và tập join point quan sát được

Một câu hỏi nâng cao là: **weaver thứ hai có nhìn thấy mã mà weaver thứ nhất đã chèn không?**

Ví dụ:

~~~text
P0 = classes gốc

W1(P0) = classes gốc + helper được tạo
W2(W1(P0)) = W2 có thể nhìn thấy helper

W2(P0) = chỉ nhìn thấy classes gốc
W1(W2(P0)) = helper được tạo sau khi W2 hoàn tất
~~~

Trong cơ chế mà `W2` chọn tất cả execution và không loại helper, hai thứ tự **có thể** tạo tập join point khác nhau. Nhưng một số AOP weaver có các quy tắc loại trừ mã sinh, xử lý cặp lời gọi/khai báo theo ngữ nghĩa nguồn hoặc không cho nhiều pass arbitrary như sơ đồ. Không nên suy việc dệt hai lần sẽ luôn thêm advice hai lần.

### 8.1 Call join point và execution join point

- **Call join point** nằm tại vị trí phát sinh lời gọi, với ngữ cảnh caller và chữ ký tại điểm gọi theo mô hình.
- **Execution join point** nằm ở phần chạy thân phương thức được hỗ trợ.

Một biến đổi tạo thêm lời gọi helper có thể thay đổi tập **call sites** trước khi weaver tiếp theo quét; một biến đổi tạo thêm phương thức có thể thay đổi tập **execution candidates**. Cả hai tác động chỉ xảy ra khi mô hình có hỗ trợ và không loại những điểm do mã sinh tạo ra.

### 8.2 Generics, bridge và bytecode sau biên dịch

Trong Java, generic type erasure có thể đổi descriptor so với chữ ký nguồn; compiler đôi khi sinh **bridge methods** để giữ dispatch của override. Nếu một công cụ xử lý bytecode **sau biên dịch**, nó có thể thấy các thành phần này. Nhưng Reflection nhìn thấy bridge không chứng minh AOP sẽ coi bridge là một execution join point riêng.

Cần phân biệt:
- **Kết quả compiler sinh:** sự tồn tại của bridge/synthetic members trong class file.
- **Bộ chọn của weaver:** thành phần nào được công nhận là join point và pointcut nào match.
- **Thứ tự biến đổi:** thành phần nào được tạo/đổi trước khi bộ chọn chạy.

Không được chỉ nhìn số phương thức trong bytecode rồi kết luận số lần advice thực thi.

## 9. Xây dựng từng phần và kết quả dệt không đồng nhất

**Incremental build** chỉ biên dịch hoặc dệt lại những phần được đánh dấu là thay đổi. Điều này tăng tốc nhưng đặt ra trách nhiệm quản lý phụ thuộc:

- Nếu một **aspect thay đổi**, những lớp nào đang chịu pointcut của nó cần được weave lại?
- Nếu một **class thêm phương thức** mới thuộc phạm vi pointcut, build có nhận ra để cập nhật kết quả dệt không?
- Nếu **một annotation hoặc signature** đổi, các match cũ còn hợp lệ không?
- Nếu đổi cấu hình **precedence**, có cần tái tạo artifact chứa advice của nhiều aspect không?
- Nếu tool đã biến đổi một class, lần sau nó đọc **class gốc** hay **class đã dệt**?
- Nếu có cache build, key cache có bao gồm **phiên bản weaver, cấu hình và toàn bộ khai báo aspect liên quan** không?

Một incremental pipeline quản lý phụ thuộc không đầy đủ có thể tạo **artifact cũ**: một lớp còn mang thứ tự advice của bản build trước, trong khi lớp khác được weave theo cấu hình mới. Chương trình có thể vẫn chạy, khiến lỗi chỉ xuất hiện tại một số đường gọi.

**Không suy rằng “chạy lại build một lần” luôn làm sạch trạng thái.** Cần cơ chế quản lý artifact trung gian, dependency graph và invalidation phù hợp; khi nghi ngờ, đối chiếu với một **clean build** từ cùng nguồn và cấu hình.

### 9.1 Dệt lặp và vấn đề idempotency

Nếu một phép biến đổi `W` thêm instrumentation, không được mặc định:

~~~text
W(W(P)) == W(P)
~~~

Một số cách triển khai có thể thêm code lặp khi chạy hai lần, dẫn đến log hoặc metric bị đếm đôi; một số weaver có cơ chế đánh dấu, từ chối hoặc bảo đảm dệt lặp an toàn theo phạm vi hỗ trợ.

Quy trình phải xác định rõ:
- Nguồn đầu vào của mỗi pass có phải artifact **chưa dệt** hay không.
- Công cụ có hỗ trợ reweaving không, và với giới hạn nào.
- Có dấu vết/metadata để nhận biết artifact đã được weave không.
- Làm sao kiểm thử để phát hiện advice lặp, thay đổi thứ tự hoặc bỏ sót.

Không nên thử “dệt lại để chắc chắn” lên artifact đang dùng mà không biết chính sách hỗ trợ của weaver.

### 9.2 Lớp được tạo sau bước dệt

Nếu bytecode generator hoặc trình sinh mã tạo thêm class **sau** khi một weaver compile-time đã chạy, class mới có thể không được weave trong pass đó. Ngược lại, một lớp được tạo **trước** có thể nằm trong tập ứng viên nếu cơ chế quét thấy nó.

Với mô hình load-time, các lớp được tạo và nạp sau có thể chịu biến đổi theo cấu hình đang hoạt động. Nhưng điều này không tự bảo đảm các lớp do nhiều class loader tạo đều được xử lý giống nhau.

## 10. Tái lập kết quả dệt (reproducibility)

Để so sánh hai bản build, phải kiểm soát **đầu vào đầy đủ**, không chỉ repository commit:

| Yếu tố | Vì sao ảnh hưởng |
| --- | --- |
| Phiên bản compiler/JDK | Bytecode, synthetic/bridge methods và một số metadata có thể khác |
| Phiên bản weaver | Bộ chọn điểm, mã phát sinh và lỗi đã sửa có thể khác |
| Khai báo aspect/pointcut | Quyết định tập join point và advice |
| Quy tắc precedence | Quyết định hành vi khi nhiều advice cùng khớp |
| Classpath/module path | Kiểu, lớp, thư viện và phụ thuộc hiện diện khi build |
| Thứ tự pipeline | Biến đổi nào xem biểu diễn trước/sau |
| Generated sources/classes | Những thành phần nào tồn tại trước pass weaving |
| Build cache/incremental state | Artifact có được tái tạo đúng sau thay đổi không |
| Runtime agent/class loader | Với load-time weaving, cấu hình tải lớp có ảnh hưởng |
| Tham số build/profile | Điều kiện bật/tắt instrumentation và môi trường áp dụng |

Một quá trình kiểm chứng có thể:
1. Ghi lại phiên bản công cụ và cấu hình precedence.
2. Clean build từ nguồn xác định.
3. Xuất **báo cáo join point được chọn** hoặc log weaving nếu công cụ hỗ trợ.
4. Chạy kiểm thử thứ tự advice, kết quả và ngoại lệ.
5. So sánh với incremental build từ cùng nguồn.
6. Kiểm tra cả artifact lớp cụ thể và đường gọi thực tế, không chỉ trạng thái “BUILD SUCCESS”.

### 10.1 Mã băm artifact có ý nghĩa gì?

Hash artifact giúp xác định hai tệp **có giống byte** hay không. Nếu hash khác, cần phân tích xem vì timestamp/metadata hay khác code. Nếu hash giống nhau, hai artifact đó đồng nhất byte; nhưng kết quả runtime còn có thể phụ thuộc **agent, classpath, cấu hình và môi trường nạp lớp**.

Hash **không thay thế** kiểm thử hành vi, nhất là với weaving khi nạp lớp hoặc proxy tạo runtime.

## 11. Xung đột giữa nhiều aspect và nhiều công cụ instrument

Không chỉ nhiều advice, một ứng dụng có thể có **nhiều trình biến đổi mã**: weaver AOP, bộ theo dõi coverage, profiler, công cụ theo dõi tracing hoặc bytecode enhancement.

Các công cụ có thể:
- Chèn phương thức hoặc field trợ giúp.
- Sửa lời gọi hoặc bytecode điều khiển ngoại lệ.
- Tạo try/finally và xử lý stack/metadata.
- Sinh proxy hoặc điều chỉnh đường dispatch.
- Yêu cầu đầu vào đúng một dạng class file nhất định.

Nếu chạy hai công cụ theo thứ tự khác, một công cụ có thể quét **mã đã instrument** thay vì mã nguồn ban đầu. Có thể xuất hiện log lặp, chi phí tăng, lỗi verification, điểm không còn khớp hoặc mất metadata.

**Cách phòng tránh:**
- Đọc hợp đồng tương thích và thứ tự áp dụng mà **chính các công cụ** công bố.
- Chỉ dùng pipeline có thứ tự rõ ràng, được kiểm thử trên phiên bản cụ thể.
- Tránh dùng cấu hình ngầm hoặc thứ tự tác nhân runtime không được bảo đảm.
- Theo dõi danh tính artifact đầu vào/đầu ra mỗi pass.
- Thử nhánh lỗi, dọn tài nguyên và concurrency, không chỉ “phương thức vẫn trả đúng chuỗi”.

Không phải cặp biến đổi nào cũng gây xung đột; mục tiêu là **nhận diện những tương tác có thể làm thay đổi tập điểm hoặc ngữ nghĩa**.

## 12. Những hệ quả về bảo mật và transaction

### 12.1 Bảo mật cần ranh giới không bị bỏ qua

Giả sử cấu trúc:

~~~text
Cache(Authorize(Business))
~~~

Nếu cache nằm ngoài và có quyền trả sớm khi hit, `Authorize` bên trong **không chạy**. Nếu yêu cầu nào cũng phải kiểm tra quyền, đây là lỗi kiến trúc dù từng advice được viết đúng.

Cấu trúc:

~~~text
Authorize(Cache(Business))
~~~

đặt kiểm tra quyền trước nhánh cache; nhưng vẫn phải đảm bảo mọi lối vào cần bảo vệ đi qua lớp ngoài và chính sách được đánh giá trên thông tin đáng tin.

Khi build/weaving thay thứ tự bọc, bất biến “kiểm tra quyền trước khi tiết lộ dữ liệu” có thể bị phá mà không có lỗi biên dịch.

### 12.2 Transaction và retry

Hai thứ tự:

~~~text
Retry(Transaction(Business))
Transaction(Retry(Business))
~~~

có thể tạo ngữ nghĩa khác nhau:

- Retry ở ngoài có thể tạo **giao dịch riêng cho từng lần thử**, nếu cách xây dựng transaction thực sự mở/đóng giao dịch quanh mỗi `proceed`.
- Transaction ở ngoài có thể giữ **một ranh giới giao dịch** cho nhiều lần thử, làm các lỗi trước ảnh hưởng trạng thái những lần sau.

Không được kết luận chỉ từ tên advice rằng một lần retry sẽ luôn tạo giao dịch mới; điều đó còn phụ thuộc API transaction và cách advice tổ chức tài nguyên thật. Với thao tác có tác dụng phụ, cần tính đến idempotency và chính sách rollback.

### 12.3 Audit và kết quả dệt

Một audit advice nằm trong lớp có thể short-circuit có thể không thấy các yêu cầu bị trả sớm. Một audit nằm ở ngoài có thể ghi được mọi yêu cầu tới lớp ngoài, nhưng vẫn phải giới hạn dữ liệu nhạy cảm được thu thập.

“Có audit aspect” không đủ chứng minh tất cả sự kiện phải kiểm toán đều được ghi. Cần biết **nơi dệt và vị trí advice trong chuỗi**.

## 13. Kiểm thử kiến trúc thay vì chỉ kiểm thử build thành công

Một ma trận tối thiểu:

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Hai advice cùng khớp một execution join point | Thứ tự vào/ra theo precedence đã công bố |
| Đổi thứ tự liệt kê wrapper | Thay đổi kết quả đúng theo thuật toán ghép, hoặc không đổi nếu có quy tắc thứ tự rõ |
| Thêm class/overload mới | Pointcut match đúng tập điểm, không bỏ sót/thừa |
| Aspect đổi pointcut | Incremental build invalidates artifact chịu tác động |
| Clean vs incremental build | Cấu trúc advice và hành vi tương đương |
| Chạy lại weaver trên artifact đã dệt | Không sinh đếm trùng ngoài hợp đồng hỗ trợ |
| Lỗi trong business | Advice error/finally và ngoại lệ gốc đúng thứ tự |
| Around short-circuit | Advice bên trong không chạy; invariants vẫn được bảo vệ |
| Lời gọi qua proxy và lời gọi trực tiếp | Biết đường nào được instrument |
| Class được nạp trước/sau tác nhân weaving | Phạm vi load-time khớp cấu hình thực tế |
| Nhiều công cụ transform cùng class | Không mất metadata, sai stack hoặc đổi hành vi ngoài ý muốn |
| Bảo mật/giao dịch/audit | Những ràng buộc bắt buộc vẫn đúng với thứ tự hiệu lực |

### 13.1 Dùng trace để kiểm tra thứ tự

Có thể thu thập một danh sách sự kiện tuần tự **trong cùng một phép thử đồng bộ**:

~~~text
[
    "Security.before",
    "Transaction.before",
    "Business",
    "Transaction.after",
    "Security.after"
]
~~~

Đó là một **expected trace của cấu trúc lồng nhau đã định nghĩa**, không phải thứ tự mặc định của mọi hệ thống AOP. Khi có nhiều thread hoặc hệ thống log bất đồng bộ, thứ tự dòng log xuất hiện ở nơi thu thập có thể không phản ánh toàn bộ quan hệ thực thi; nên dùng trace/correlation và các assertion đúng phạm vi.

### 13.2 So sánh artifact và hành vi

Nếu được, nên có hai nhóm kiểm chứng:

- **Kiểm chứng cấu trúc:** danh sách join point/advice được dệt, loại mã phát sinh và vị trí áp dụng; có thể dùng báo cáo weaver, inspection bytecode hoặc metadata do công cụ công bố.
- **Kiểm chứng hành vi:** test các đường vào, đường ra, ngoại lệ, short-circuit, retry và tác dụng phụ.

Một ảnh chụp mã cuối hoặc một bài test log đơn lẻ không đủ chứng minh toàn bộ chính sách an ninh vẫn hoạt động.

## 14. Các lỗi hiểu sai phổ biến

1. **“Xây dựng A trước B nên A chạy before trước B.”** Không nhất thiết; precedence và thuật toán kết hợp quyết định thứ tự có hiệu lực.
2. **“Thêm wrapper trước nghĩa là wrapper ở ngoài.”** Sai với vòng lặp `chain = Wrap(next, chain)` như ví dụ; phần thêm sau ở ngoài.
3. **“Dệt ở compile time luôn tốt hơn dệt lúc chạy.”** Mỗi thời điểm có ưu/nhược về tập join point, tính linh hoạt, hiệu năng và vận hành.
4. **“Hai phép biến đổi có thể đổi chỗ mà không ảnh hưởng.”** Chưa chắc: chúng có thể không giao hoán và có thể thay đổi tập join point.
5. **“Có bridge method thì chắc chắn thêm execution advice.”** Sai nếu mô hình loại bridge hoặc định nghĩa join point khác.
6. **“Clean build và incremental build thành công là tương đương.”** Chỉ khi invalidation và đầu vào đã được quản lý đúng; cần đối chiếu.
7. **“Dệt một lần nữa chắc không thay đổi gì.”** Không có bảo đảm idempotency chung.
8. **“Đổi thứ tự build làm đổi ưu tiên advice trong mọi công cụ.”** Sai; nhiều công cụ xác định precedence độc lập với thứ tự build.
9. **“Cùng một tệp class nghĩa là runtime weaving/proxy chắc chắn giống nhau.”** Runtime agent, class loader và cấu hình có thể thay đổi lớp can thiệp.
10. **“Kết quả dệt chỉ cần so hash.”** Hash khác chưa chắc sai hành vi; hash giống chưa chắc bao phủ điều kiện runtime khác.
11. **“Thứ tự after giống before.”** Trong wrapper lồng nhau, phần thoát thường ngược chiều phần vào.
12. **“Mọi advice đều chạy vì đều match pointcut.”** Advice bao ngoài có thể chặn không gọi tiếp, hoặc đường gọi không được weave.
13. **“Thêm aspect chỉ ảnh hưởng nó.”** Aspect mới có thể thay thứ tự, ranh giới transaction hoặc trạng thái ngoại lệ các lớp hiện có.
14. **“Dùng tên class được sinh làm quy tắc build vĩnh viễn.”** Generated class, synthetic name và thứ tự compiler có thể thay giữa công cụ/phiên bản.

## 15. Checklist thiết kế pipeline weaving

Khi đưa AOP vào build hoặc thay đổi kiến trúc dệt, nên ghi lại:

- [ ] **Loại join point** thật sự cần: call, execution hay loại được công cụ hỗ trợ.
- [ ] **Thời điểm weaving:** nguồn, compile-time, post-compile, load-time, runtime proxy hay nhiều bước.
- [ ] **Input của mỗi bước**: mã nguồn, class chưa dệt hay class đã instrument?
- [ ] **Thứ tự các phép biến đổi:** công cụ nào chạy trước, do đâu bảo đảm?
- [ ] **Quy tắc precedence:** aspect/advice nào bao ngoài, quy tắc tie-break và trường hợp đồng mức.
- [ ] **Mã sinh và generic:** bridge/synthetic/generated methods có được xem xét không?
- [ ] **Build dependencies:** đổi aspect/pointcut/precedence có làm những lớp liên quan được weave lại không?
- [ ] **Tái dệt:** cơ chế hỗ trợ reweaving hay có nguy cơ chèn lặp?
- [ ] **Tái lập:** phiên bản JDK, weaver, classpath, config và cache key có được cố định không?
- [ ] **Bất biến nghiệp vụ:** auth, transaction, audit, retry, cleanup có còn đúng khi thứ tự đổi?
- [ ] **QA:** có test thứ tự trước/sau, success/error, short-circuit và direct/proxy paths không?
- [ ] **Quan sát:** có bằng chứng từ artifact hoặc report weaving cùng trace runtime không?

## 16. Bài tập suy luận

### Bài 1: Builder bọc lần lượt

Cho:

~~~text
pipeline = Business
pipeline = Wrap(Log, pipeline)
pipeline = Wrap(Security, pipeline)
~~~

**Hỏi:** lớp nào chạy before trước?

**Đáp:** `Security` ở ngoài `Log`, nên trong mô hình wrapper thông thường: `Security.before → Log.before → Business`. Khi thành công, hậu xử lý theo đường đi ra thường là `Log.after → Security.after`.

### Bài 2: Dệt hai pass

`W1` sinh thêm method `helper()`; `W2` chọn method execution theo tên/phạm vi. Đổi từ `W2(W1(P))` sang `W1(W2(P))` có chắc giữ cùng tập điểm?

**Đáp:** không. `W2` có thể thấy `helper` ở thứ tự đầu và không thấy ở thứ tự sau. Nhưng kết quả cuối còn phụ thuộc quy tắc hỗ trợ join point/mã sinh của `W2`; không tự khẳng định mọi helper sẽ được weave.

### Bài 3: Precedence và thứ tự tệp

Một chương trình có aspect Audit và Timer. Tên tệp Audit đứng trước Timer trong thư mục. Có đủ để xác định Audit chạy trước Timer không?

**Đáp:** không. Thứ tự tệp/thư mục không phải hợp đồng precedence trừ khi công cụ đã quy định tường minh, điều thường không nên dựa vào để thiết kế.

### Bài 4: Cùng code nhưng build khác

Clean build chạy đúng, incremental build sau khi đổi pointcut lại thiếu advice tại một lớp. Khả năng nào cần kiểm tra?

**Đáp:** invalidation của class chịu pointcut, cache key, artifact đã dệt cũ, thứ tự build, danh sách generated classes và cấu hình weaver có được đưa vào quyết định build lại không.

### Bài 5: Thay đổi thứ tự thành lỗi bảo mật

Một cache được đưa từ trong ra ngoài lớp authorization. Cache hit không gọi tiếp. Có thể có vấn đề gì?

**Đáp:** authorization nằm trong cache có thể không chạy khi hit, khiến người không đủ quyền nhận dữ liệu nếu không có rào chắn tương đương. Phải xác định lại precedence và bảo đảm kiểm tra quyền trước trả dữ liệu.

### Bài 6: Lời gọi tiếp nhiều lần

Một advice Retry bao ngoài Transaction và gọi continuation ba lần. Có thể nói luôn rằng ba transaction được tạo không?

**Đáp:** chỉ khi cách kết hợp thật sự cho phép mỗi lần tiếp tục đi qua vùng tạo transaction mới và runtime cung cấp ngữ nghĩa tương ứng. Không suy từ tên advice; cần test phạm vi transaction.

## 17. Kết luận

**Thứ tự xây dựng** xác định các bước tạo và biến đổi chương trình; **thứ tự dệt** xác định phép biến đổi nào nhìn thấy biểu diễn nào; **precedence** xác định các advice được kết hợp ra sao; còn **thứ tự chạy** phản ánh chuỗi có hiệu lực lúc chương trình thực thi.

Bốn thứ tự có liên quan nhưng không đồng nhất. Nếu phép biến đổi **không giao hoán**, đổi thứ tự có thể làm khác mã cuối, tập join point hoặc kết quả trả về. Nếu cơ chế AOP định nghĩa precedence và pipeline ổn định, việc đảo thứ tự xử lý tệp **có thể không ảnh hưởng** tới hành vi. Điều cần kiểm chứng là **artifact, tập điểm được dệt và các bất biến runtime**, nhất là khi có nhiều aspect, nhiều weaver, build tăng dần hoặc proxy/runtime weaving.

**Ghi nhớ:** Đừng đoán thứ tự advice từ tên file, thứ tự compile hoặc thứ tự khai báo. Hãy đọc hợp đồng của cơ chế weaving, mô tả rõ thuật toán kết hợp, kiểm thử đường thành công/lỗi và so sánh clean/incremental build để đảm bảo kết quả dệt đúng ý định.
