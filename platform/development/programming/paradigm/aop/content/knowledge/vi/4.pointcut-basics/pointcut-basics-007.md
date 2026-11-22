# Kết hợp điều kiện bằng phép và, hoặc và phủ định trong Pointcut

## Mục tiêu bài học

Một **pointcut** mô tả **tập join point** mà tại đó hành vi xuyên suốt (*advice*) sẽ được áp dụng. Trên một hệ thống nhỏ, tiêu chí “mọi lần thực thi của phương thức được đánh dấu cần quan sát” có thể đủ. Trong chương trình thực tế, yêu cầu thường chi tiết hơn: “theo dõi các thao tác ghi **hoặc** các thao tác có marker, **nhưng không** theo dõi mã nội bộ của hệ thống đo lường”. Khi đó, cần **kết hợp điều kiện** bằng ba phép toán logic:

- **VÀ (AND):** Cả hai điều kiện đều đúng.
- **HOẶC (OR):** Ít nhất một trong các điều kiện đúng.
- **PHỦ ĐỊNH (NOT):** Điều kiện được phủ định không đúng.

Ví dụ khái niệm:

```text
(chọn thao tác ghi OR chọn thao tác có marker)
AND NOT chọn thao tác nội bộ
```

Đây là **giả mã** minh họa tư duy, không phải cú pháp pointcut có thể dán vào mọi công cụ AOP. Các công cụ có thể dùng `&&`, `||`, `!`, từ khóa `and/or/not`, API predicate hoặc cú pháp khác. Điều phải giữ nguyên là **ngữ nghĩa chọn tập sự kiện** và quy tắc nhóm bằng dấu ngoặc.

Sau bài này, bạn có thể tự thiết kế một pointcut ghép, dựng bảng chân trị, dùng De Morgan để diễn giải phủ định, phát hiện điều kiện mâu thuẫn/quá rộng, hiểu giới hạn của phép NOT, và kiểm thử một ví dụ Java 17 hoạt động ở runtime.

## 1. Điều kiện pointcut áp dụng lên cái gì?

AOP coi một **join point** là một điểm/sự kiện có thể can thiệp trong quá trình chạy, chẳng hạn một lần *method execution* hoặc một lần *method call*, tùy **join-point model** của công cụ. Một **pointcut** chọn các điểm trong phạm vi mà công cụ hỗ trợ.

Hãy ký hiệu:

- \(U\): tập các join point mà ta đang xét và cơ chế có khả năng nhận diện.
- \(A\): tập các join point thỏa quy tắc A.
- \(B\): tập các join point thỏa quy tắc B.
- \(C\): tập các join point thỏa quy tắc C.

Ví dụ:

- \(A\) = các lần thực thi phương thức thuộc nhóm *storage*.
- \(B\) = các lần thực thi phương thức được đánh dấu cần theo dõi.
- \(C\) = các lần thực thi phương thức thuộc nhóm *internal instrumentation*.

Mỗi quy tắc tương ứng với một mệnh đề đúng/sai tại **cùng một join point đang xét**. Điều kiện ghép có ý nghĩa là **lọc giao, hợp hoặc phần bù** của các tập trong \(U\).

Quan trọng: \(U\) **không phải tập mọi dòng mã trong dự án**. Nó chỉ bao gồm những điểm thuộc loại được mô hình AOP/cơ chế đang xét hỗ trợ. Một dynamic proxy theo interface có thể quan sát lời gọi đi **qua proxy**, nhưng không tự biến mọi method body và mọi vị trí gọi trong chương trình thành điểm có thể chặn. Vì vậy, `NOT A` không thể làm xuất hiện join point ở những nơi công cụ vốn không quan sát được.

### 1.1. Một biểu thức tĩnh có thể khớp nhiều lần thực thi

Đoạn mã:

```java
for (int i = 0; i < 4; i++) {
    repository.save(i);
}
```

Chỉ có **một vị trí gọi** trong source nhưng có thể có **bốn sự kiện gọi ở runtime**. Nếu loại join point và đường can thiệp phù hợp, pointcut ghép sẽ được áp dụng đối với những lần thực sự xảy ra. Điều kiện động (ví dụ đối số `i > 1`) có thể đúng ở một số lượt và sai ở những lượt còn lại.

Phép toán logic nói “**sự kiện nào được chọn**”, không tự quyết định “**sự kiện sẽ xảy ra bao nhiêu lần**”.

## 2. Phép VÀ (AND): lấy phần giao

Định nghĩa trên từng join point:

```text
A AND B = true   chỉ khi A=true và B=true
```

Theo tập hợp: \(A \land B\) chọn \(A \cap B\).

| A | B | A AND B |
| --- | --- | --- |
| false | false | false |
| false | true | false |
| true | false | false |
| true | true | true |

### 2.1. Ví dụ: vừa thuộc phạm vi, vừa có marker

Giả sử A là “method thuộc nhóm thao tác nhập dữ liệu”, B là “method có marker `@Observed`”. Khi dùng `A AND B`, chỉ những method **đồng thời** đáp ứng hai tiêu chí mới được chọn.

Điều này chặt hơn từng tiêu chí riêng:

- Một thao tác nhập dữ liệu **không** có marker → bị loại.
- Một method có marker nhưng thuộc nhóm đo đạc nội bộ → bị loại nếu nó không thuộc nhóm nhập dữ liệu.
- Một thao tác nhập dữ liệu có marker → được chọn, nếu đúng loại join point và đường can thiệp được hỗ trợ.

Giả mã:

```text
execution(method thuộc nhóm import)
AND methodHasMarker("Observed")
```

Từ `execution`, `methodHasMarker` ở đây là tên tự mô tả để minh họa; **không phải designator chuẩn cho mọi ngôn ngữ/công cụ AOP**.

### 2.2. Hai điều kiện có thể luôn mâu thuẫn

Nếu A chọn **method-call join point**, B chọn **method-execution join point**, trong một mô hình phân biệt hai loại sự kiện loại trừ nhau, thì `A AND B` không thể đúng với cùng một join point. Việc cả hai có liên quan đến “cùng method” không khiến chúng trở thành cùng loại sự kiện.

Tương tự:

```text
A AND NOT A
```

luôn sai với cùng một sự kiện nếu A là predicate logic nhất quán. Kết quả là **pointcut không chọn điểm nào**, không có nghĩa advice của công cụ đang bị hỏng.

### 2.3. Lưu ý về điều kiện động

Với yêu cầu “method được đánh dấu **và** giá trị đối số phải hợp lệ”, phần marker có thể nhận biết từ metadata, nhưng giá trị đối số chỉ biết theo từng lời gọi runtime. Không phải mọi hệ thống AOP đều hỗ trợ matcher đối số động theo cùng cách. Phép AND là tư duy logic chung; khả năng truy cập đối số và thời điểm đánh giá tùy công nghệ.

## 3. Phép HOẶC (OR): lấy phần hợp

Định nghĩa:

```text
A OR B = true   khi A=true, B=true, hoặc cả hai cùng true
```

Theo tập hợp: \(A \lor B\) chọn \(A \cup B\).

| A | B | A OR B |
| --- | --- | --- |
| false | false | false |
| false | true | true |
| true | false | true |
| true | true | true |

### 3.1. Ví dụ: chọn theo nhóm hoặc marker

Giả sử:

- A = các lần thực thi method có tên bắt đầu bằng `create`.
- B = các lần thực thi method được đánh dấu `@Tracked`.

Biểu thức:

```text
methodNameStartsWith("create")
OR methodHasMarker("Tracked")
```

sẽ chọn **cả** phương thức `createDraft` không có marker **lẫn** phương thức `submit` có marker. Một phương thức `createInvoice` đồng thời có marker chỉ được kết luận là **khớp biểu thức OR**; bản thân biểu thức Boolean không nói rằng advice phải chạy **hai lần**.

**Phân biệt hai việc:**

1. **Một pointcut ghép** `A OR B` gắn với **một advice**: nếu join point khớp cả A và B, về mặt logic nó vẫn là một điểm được chọn bởi pointcut ghép.
2. **Hai advice/aspect riêng biệt**, một gắn A và một gắn B: nếu cùng join point khớp cả hai, **cả hai advice đều có thể chạy**. Tần suất và thứ tự thực tế còn phụ thuộc engine và cấu hình.

Đếm “hai điều kiện true” rồi suy ra “hai lần chạy của một advice” là lỗi logic.

### 3.2. OR thường mở rộng phạm vi ngoài dự tính

Điều kiện `A OR B` chọn **nhiều hoặc bằng** từng tập A, B. Nếu B vô tình là “mọi method public”, OR gần như nuốt toàn bộ giới hạn ở A đối với method public. Cần rà soát nhánh OR có phạm vi rộng nhất.

Một tiêu chí OR cũng có thể đưa vào những method vốn phải loại trừ: nhánh mới thêm sau này có thể khớp chức năng nội bộ, mã chứa dữ liệu nhạy cảm hoặc đường cực kỳ nóng. Vì vậy, trong nhiều thiết kế, nên đặt điều kiện loại trừ **ngoài toàn bộ nhóm OR**.

## 4. Phép PHỦ ĐỊNH (NOT): lấy phần bù trong tập được xét

Định nghĩa:

```text
NOT A = true   khi A=false
```

| A | NOT A |
| --- | --- |
| false | true |
| true | false |

Theo tập hợp, NOT A là \(U \setminus A\), phần bù của A **trong tập \(U\)**.

### 4.1. Dùng NOT để loại trừ mã nội bộ

Ví dụ: cần ghi log cho thao tác có marker nhưng không ghi log cho chính bộ logging.

```text
methodHasMarker("Observed")
AND NOT belongsToInternalLogging()
```

Đây là biểu thức phạm vi có ích vì nó tránh một số vòng lặp reentrant:

```text
advice -> logger -> method nội bộ -> advice -> logger -> ...
```

Tuy nhiên, không phải chỉ cần một phép NOT là đủ bảo đảm tránh mọi đệ quy. Phải xác định logger gọi những method nào, công cụ đang chặn loại join point nào, và liệu có đường gọi phụ trợ khác vẫn lọt vào pointcut.

### 4.2. NOT đơn lẻ rất dễ quá rộng

```text
NOT methodHasMarker("Internal")
```

có thể chọn **mọi join point mà công cụ thấy được** không có marker nội bộ: method nghiệp vụ, utility, thao tác hệ thống, mã mới thêm sau này... Nếu mục đích chỉ là chọn phương thức xử lý lệnh ở module cụ thể, nên giới hạn dương trước:

```text
belongsToModule("command")
AND NOT methodHasMarker("Internal")
```

NOT thường có giá trị cao nhất khi dùng như **điều kiện loại trừ rõ ràng** sau một tập chọn dương đủ hẹp.

### 4.3. NOT không mở rộng năng lực can thiệp

Nếu công cụ chỉ bắt lời gọi qua proxy, `NOT withinInternalModule()` không làm nó chặn được lời gọi trực tiếp đến target hay field access. Nếu một loại join point chưa được hỗ trợ, phủ định một điều kiện trên loại đó cũng không “đưa loại đó vào \(U\)”. Mọi phép phủ định đều phải hiểu tương đối với **mô hình join point và phạm vi weaving**.

## 5. Kết hợp cả ba phép toán: dấu ngoặc quyết định tập kết quả

Xét ba điều kiện:

- **A:** Tên method bắt đầu bằng `create`.
- **B:** Method được gắn marker `@Tracked`.
- **C:** Method được gắn marker `@Internal`.

Yêu cầu: “Chọn method thuộc nhóm tạo **hoặc** có marker theo dõi, **trừ** method nội bộ”.

Viết đúng ý định:

```text
(A OR B) AND (NOT C)
```

Không đồng nghĩa với:

```text
A OR (B AND (NOT C))
```

Trong biểu thức thứ hai, nhánh A **không chịu** điều kiện loại trừ C: một method `createInternal` vừa thỏa A vừa thỏa C vẫn được chọn.

### 5.1. Bảng chân trị để phát hiện sai lầm

| A | B | C | (A OR B) AND NOT C | A OR (B AND NOT C) |
| --- | --- | --- | --- | --- |
| false | false | false | false | false |
| false | false | true | false | false |
| false | true | false | true | true |
| false | true | true | false | false |
| true | false | false | true | true |
| true | false | true | **false** | **true** |
| true | true | false | true | true |
| true | true | true | **false** | **true** |

Hai hàng có `A=true`, `C=true` cho thấy hậu quả: biểu thức thứ hai **bỏ qua loại trừ nội bộ** đối với cả nhóm create.

### 5.2. Độ ưu tiên và dấu ngoặc

Trong đại số Boolean và những cú pháp thông dụng có ưu tiên toán tử chuẩn, thứ tự thường là:

1. **NOT** áp lên biểu thức ngay sau nó.
2. **AND** liên kết hai mệnh đề.
3. **OR** hợp các mệnh đề.

Vì vậy `A OR B AND NOT C` thường được hiểu là `A OR (B AND (NOT C))`, **không phải** `(A OR B) AND (NOT C)`. Tuy nhiên, không giả định cú pháp hoặc độ ưu tiên của mọi ngôn ngữ pointcut đều giống Java. Đối với pointcut có nhiều toán tử, **luôn dùng dấu ngoặc tường minh** theo đúng tài liệu của công cụ.

Về ý nghĩa, hãy đọc từ ngoài vào trong: “**chọn (A hoặc B), sau đó loại trừ C**”. Cách diễn đạt này thường giúp nhận ra chỗ đặt ngoặc đúng.

### 5.3. Dấu ngoặc không quy định thứ tự chạy advice

`(A OR B) AND NOT C` là **điều kiện lựa chọn**; nó không nói “chạy A trước B”, “chạy B sau C” hay “AOP sẽ kiểm tra runtime theo thứ tự trái sang phải”. Thứ tự chạy nhiều advice do **precedence/order** và cơ chế weaving quyết định.

Trong một phép tính Boolean Java thuần dùng `&&`/`||`, ngôn ngữ có **short-circuit evaluation** từ trái qua phải. Nhưng không nên áp quy tắc đánh giá biểu thức Java đó cho mọi pointcut DSL hoặc engine tối ưu/weave matcher. Một công cụ có thể giản lược điều kiện tĩnh, sắp xếp lại bộ lọc nội bộ hoặc biến đổi thành cấu trúc khác miễn vẫn giữ **ngữ nghĩa matching** mà nó công bố.

**Không viết pointcut với ý định tạo side effect dựa trên thứ tự đánh giá predicate**, vì pointcut là công cụ chọn điểm, không phải luồng xử lý nghiệp vụ.

## 6. Các luật Boolean hữu ích khi thiết kế pointcut

Các luật dưới đây đúng với **predicate logic thuần**, tức điều kiện biểu diễn mệnh đề đúng/sai nhất quán trên cùng vũ trụ join point. Kết quả áp dụng thực tế vẫn phải xét năng lực matcher/công cụ.

| Luật | Biểu thức tương đương | Ý nghĩa với pointcut |
| --- | --- | --- |
| Giao hoán AND | `A AND B = B AND A` | Đổi thứ tự hai tiêu chí không đổi tập join point được chọn. |
| Giao hoán OR | `A OR B = B OR A` | Đổi nhánh OR không đổi tập được chọn. |
| Kết hợp AND | `(A AND B) AND C = A AND (B AND C)` | Có thể nhóm lại các tiêu chí bắt buộc. |
| Kết hợp OR | `(A OR B) OR C = A OR (B OR C)` | Có thể nhóm lại các tập chấp nhận. |
| Phân phối | `A AND (B OR C) = (A AND B) OR (A AND C)` | Một giới hạn A áp dụng lên cả hai nhánh B, C. |
| Hấp thụ | `A OR (A AND B) = A` | Nhánh `A AND B` thừa khi đã có A. |
| Lũy đẳng | `A AND A = A`; `A OR A = A` | Lặp lại tiêu chí không làm nhân số lần chạy advice. |
| Bù trừ | `A AND NOT A = false`; `A OR NOT A = true` | Điều kiện luôn sai hoặc luôn đúng trong vũ trụ đang xét. |
| Phủ định kép | `NOT (NOT A) = A` | Hai lần phủ định triệt tiêu nhau. |

### 6.1. Hai định luật De Morgan

```text
NOT (A OR B) = (NOT A) AND (NOT B)
NOT (A AND B) = (NOT A) OR (NOT B)
```

Đọc bằng lời:

- **Không thuộc A hoặc B** nghĩa là **không thuộc A và cũng không thuộc B**.
- **Không đồng thời thuộc A và B** nghĩa là **ít nhất một trong hai điều kiện không đúng**.

Ví dụ muốn loại trừ **cả hai nhóm** `Internal` và `Generated`, cách diễn đạt chính xác là:

```text
base
AND NOT (Internal OR Generated)
```

tương đương:

```text
base
AND NOT Internal
AND NOT Generated
```

Cách viết sai thường thấy:

```text
base
AND (NOT Internal OR NOT Generated)
```

Biểu thức sai chỉ loại khi **đồng thời** Internal và Generated, còn phần lớn trường hợp chỉ thuộc một nhóm vẫn được chọn.

### 6.2. Cần phân biệt tương đương logic và khả năng biên dịch

Hai biểu thức có thể tương đương trên giấy nhưng công cụ AOP có thể giới hạn vị trí xuất hiện của toán tử, kiểu designator, ràng buộc biến hoặc binding context. Ví dụ, một số matcher cần một binding nhất quán trong các nhánh OR; tên biến lấy từ một nhánh có thể không sẵn ở nhánh kia. Vì vậy:

1. Chứng minh hai biểu thức cùng tập matching về mặt logic.
2. Xác minh **cú pháp, binding và join-point model** cho phép biểu diễn chúng.
3. Kiểm thử bằng các điểm thuộc/không thuộc phạm vi mong muốn.

Không sửa một điểm cắt chỉ vì “rút gọn Boolean chắc chắn tương đương” mà bỏ qua quy tắc binding cụ thể.

## 7. Biểu thức ghép của pointcut không giống điều kiện nghiệp vụ

Một pointcut chọn **khi nào advice được kích hoạt**. Nó không thay thế quy tắc tính tiền, quyết định trạng thái hay kiểm tra toàn vẹn dữ liệu nghiệp vụ.

Ví dụ điều kiện nghiệp vụ:

```text
khách có quyền sửa tài liệu
AND tài liệu chưa khóa
AND hạn cập nhật chưa hết
```

Đây là **quy tắc cấp quyền/thay đổi trạng thái** của domain. Dù có thể biểu diễn bằng AND/OR/NOT, đặt nó hoàn toàn trong advice vô hình sẽ làm khó truy vết và dễ tạo lỗ hổng nếu có đường gọi bypass cơ chế AOP. Hãy dùng domain service/policy và kiểm tra tại biên tin cậy; nếu cần, AOP có thể bổ sung xử lý kỹ thuật ở những điểm đã chứng minh được phạm vi.

Một điểm cắt phù hợp hơn:

```text
(method thuộc nhóm quan sát OR có marker "Observed")
AND NOT method nội bộ của bộ đo
```

Biểu thức này nói về **phạm vi thu thập quan sát**, không phải cách quyết định một kết quả nghiệp vụ.

## 8. Ví dụ Java 17 chạy được: dùng OR rồi AND NOT tại runtime

Java tiêu chuẩn không tự cung cấp một engine pointcut tổng quát. Ta có thể mô phỏng cách **kết hợp predicate** thông qua `java.lang.reflect.Proxy`: mỗi lần caller gọi method qua proxy, handler đánh giá quy tắc:

```text
(A OR B) AND NOT C

A = tên method bắt đầu bằng "create"
B = method interface có @Tracked
C = method interface có @Internal
```

**Mục đích của ví dụ** là chứng minh kết hợp điều kiện, thứ tự chọn điểm và giới hạn call path. Nó **không** có ngôn ngữ pointcut đầy đủ, không hỗ trợ mọi join point và không biểu diễn được năng lực của các cơ chế weaving khác.

Tạo tệp `PointcutBooleanDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class PointcutBooleanDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Tracked { }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Internal { }

    interface JobApi {
        @Tracked
        String submit(String id);

        String createDraft(String id);

        @Tracked
        @Internal
        String internalSync();

        @Internal
        String createInternal(String id);

        String status();
    }

    static final class JobService implements JobApi {
        @Override
        public String submit(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("blank id");
            }
            System.out.println("TARGET submit " + id);
            return "ACCEPTED:" + id;
        }

        @Override
        public String createDraft(String id) {
            System.out.println("TARGET createDraft " + id);
            return "DRAFT:" + id;
        }

        @Override
        public String internalSync() {
            System.out.println("TARGET internalSync");
            return "SYNCED";
        }

        @Override
        public String createInternal(String id) {
            System.out.println("TARGET createInternal " + id);
            return "INTERNAL:" + id;
        }

        @Override
        public String status() {
            System.out.println("TARGET status");
            return "READY";
        }
    }

    static JobApi observed(JobApi target) {
        return (JobApi) Proxy.newProxyInstance(
                JobApi.class.getClassLoader(),
                new Class<?>[] { JobApi.class },
                (proxy, method, args) -> {
                    boolean a = method.getName().startsWith("create");
                    boolean b = method.isAnnotationPresent(Tracked.class);
                    boolean c = method.isAnnotationPresent(Internal.class);
                    boolean selected = (a || b) && !c;

                    System.out.println("SELECT " + method.getName()
                            + "=" + selected);
                    if (selected) {
                        System.out.println("ADVICE before " + method.getName());
                    }

                    try {
                        Object result = method.invoke(target, args);
                        if (selected) {
                            System.out.println("ADVICE returning "
                                    + method.getName());
                        }
                        return result;
                    } catch (InvocationTargetException ex) {
                        if (selected) {
                            System.out.println("ADVICE throwing "
                                    + method.getName());
                        }
                        throw ex.getCause();
                    }
                }
        );
    }

    static void show(String result) {
        System.out.println("RESULT " + result);
    }

    public static void main(String[] args) {
        JobApi target = new JobService();
        JobApi proxy = observed(target);

        show(proxy.submit("P1"));
        show(proxy.createDraft("D2"));
        show(proxy.internalSync());
        show(proxy.createInternal("D3"));
        show(proxy.status());

        try {
            proxy.submit("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER " + ex.getMessage());
        }

        show(target.submit("P2"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac PointcutBooleanDemo.java
java PointcutBooleanDemo
```

Kết quả dự kiến:

```text
SELECT submit=true
ADVICE before submit
TARGET submit P1
ADVICE returning submit
RESULT ACCEPTED:P1
SELECT createDraft=true
ADVICE before createDraft
TARGET createDraft D2
ADVICE returning createDraft
RESULT DRAFT:D2
SELECT internalSync=false
TARGET internalSync
RESULT SYNCED
SELECT createInternal=false
TARGET createInternal D3
RESULT INTERNAL:D3
SELECT status=false
TARGET status
RESULT READY
SELECT submit=true
ADVICE before submit
ADVICE throwing submit
CALLER blank id
TARGET submit P2
RESULT ACCEPTED:P2
```

### 8.1. Tính từng dòng của quy tắc

| Method | A: tên `create...` | B: `@Tracked` | C: `@Internal` | `(A OR B) AND NOT C` |
| --- | --- | --- | --- | --- |
| `submit` | false | true | false | **true** |
| `createDraft` | true | false | false | **true** |
| `internalSync` | false | true | true | **false** |
| `createInternal` | true | false | true | **false** |
| `status` | false | false | false | **false** |

- `submit` được chọn nhờ **B** dù không thỏa A.
- `createDraft` được chọn nhờ **A** dù không thỏa B.
- `internalSync` có B nhưng bị **NOT C** loại.
- `createInternal` có A nhưng vẫn bị **NOT C** loại. Đây chính là ca giúp phát hiện viết sai thành `A OR (B AND NOT C)`.
- `status` không thỏa A hay B nên không được chọn.

Handler in `SELECT` cho **mọi method gọi qua proxy** để phục vụ bài học. Trong ứng dụng thật, chi phí của một handler và cách bỏ qua điểm không khớp có thể khác.

### 8.2. Vì sao `submit("")` vẫn phát sinh advice?

Điều kiện ghép chỉ dựa vào tên method và annotation, **không xét giá trị `id`**. `submit("")` vẫn thỏa B và không thỏa C, nên advice trước chạy; target kiểm tra `id` và ném `IllegalArgumentException`; handler ghi `ADVICE throwing` rồi truyền lại nguyên nhân gốc từ `InvocationTargetException`.

Từ đây thấy rõ hai lớp logic:

- **Pointcut:** chọn nơi advice chạy.
- **Business validation:** quyết định dữ liệu `id` có hợp lệ hay không.

Đừng biến pointcut thành nơi ẩn tất cả quy tắc nghiệp vụ.

### 8.3. Vì sao `target.submit("P2")` không in SELECT/ADVICE?

Lời gọi này đi thẳng vào target, **không qua proxy**. Mặc dù phương thức `submit` trên interface có marker, handler không nhận được sự kiện. Đây là **giới hạn của cách dynamic proxy ở ví dụ**, không phải khẳng định mọi công cụ AOP chỉ quan sát được lời gọi qua proxy.

### 8.4. Annotation ở interface, không phải tự kế thừa lên implementation

`Method` được handler nhận trong ví dụ là method của interface proxy. Điều kiện `method.isAnnotationPresent(...)` tra metadata ở đó. Nếu chuyển `@Tracked` hoặc `@Internal` sang implementation mà **không sửa matcher**, kết quả có thể thay đổi. Cơ chế weaving hoặc matcher khác có thể có quy tắc tìm metadata khác. Khi kiểm thử pointcut theo marker, hãy xác định **nơi annotation được khai báo và nơi matcher tìm kiếm**.

### 8.5. Một bài thực hành sửa ngoặc

Thử đổi đúng một dòng:

```java
boolean selected = a || (b && !c);
```

Bây giờ `createInternal` thỏa A nên được chọn, mặc dù C=true. Bạn sẽ thấy `SELECT createInternal=true` cùng dòng advice trước/sau cho method ấy. Hãy giữ nguyên dữ liệu thử, so sánh kết quả và giải thích bằng hàng chân trị A=true, B=false, C=true. Đây là thử nghiệm minh họa **thay đổi tập matching khi đổi dấu ngoặc**, không phải khuyến khích dùng biểu thức sai.

## 9. Khi kết hợp điều kiện tĩnh và điều kiện động

Công cụ AOP có thể chọn điểm dựa trên:

- **Thông tin tĩnh:** chữ ký method, loại join point, package, tên lớp, visibility, annotation đã được nhận diện ở build/weaving.
- **Thông tin động:** receiver thực, đối số, trạng thái runtime, context hoặc cflow nếu công cụ hỗ trợ.

Giả sử muốn theo dõi nhóm method có marker **và** những lượt có flag `debug=true`:

```text
hasMarker("Tracked")
AND runtimeDebugFlagIsTrue
```

Trong một mô hình hỗ trợ cả hai, cấu trúc method có thể là ứng viên tĩnh nhưng điều kiện debug phải kiểm tra theo **từng lần thực thi**. Nếu có 20 lượt gọi cùng method và debug chỉ true ở 5 lượt, advice sẽ được kích hoạt theo điều kiện đó ở 5 lượt, giả sử mọi lời gọi đi qua cơ chế can thiệp và không có điều kiện phụ khác.

### 9.1. OR giữa điều kiện tĩnh và động

```text
hasMarker("Critical")
OR runtimeContext("sampled") == true
```

Nếu nhánh marker luôn true cho một method, ý nghĩa logic không đòi hỏi nhánh `sampled` ảnh hưởng kết quả chọn method đó. Nhưng bạn **không được giả định** engine đánh giá nhánh động bao nhiêu lần hoặc theo thứ tự nào, trừ khi công cụ có hợp đồng về hành vi ấy.

### 9.2. Binding giá trị cần thống nhất giữa các nhánh

Một số DSL pointcut cho phép “bind” đối số, target hoặc annotation vào tên biến được advice dùng. Khi kết hợp OR, giá trị chỉ được bind ở một nhánh có thể không tồn tại trong nhánh kia. Công cụ có thể từ chối biểu thức hoặc yêu cầu binding tương thích ở mọi nhánh; không phải chỉ ghép Boolean là hợp lệ.

Ví dụ ý tưởng nguy hiểm:

```text
( matchArgument(x) OR matchMarker("Tracked") )
-> advice dùng x
```

Nếu sự kiện chỉ khớp nhánh marker, `x` đến từ đâu? Phải xử lý theo quy tắc binding cụ thể, hoặc tách pointcut/advice để hợp đồng dữ liệu rõ ràng.

## 10. Kiểu dữ liệu của điều kiện: đừng ghép các loại join point không tương thích

Các điểm trong AOP có thể được định nghĩa là method call, method execution, field get/set, constructor execution hoặc sự kiện khác, **tùy khả năng công cụ**. Nếu cùng một sự kiện không thể vừa là “call” vừa là “execution” theo model đang dùng, biểu thức:

```text
callOf("save") AND executionOf("save")
```

thường có **tập giao rỗng** dù lời gọi và thực thi liên quan đến cùng method. Tên giống nhau không đồng nghĩa hai predicate đúng tại cùng một join point.

Trong khi đó:

```text
executionOf("save") AND insideModule("storage")
```

có thể là một tập giao có nghĩa nếu cả hai matcher áp lên cùng loại điểm.

Một quy tắc OR giữa hai loại điểm khác nhau có thể có nghĩa là “chọn điểm call **hoặc** execution” nếu công cụ cho phép. Nhưng điều đó có thể dẫn tới **nhiều điểm can thiệp cho một hành động logic** (một call và một execution); hãy đánh giá ý định ghi log và khả năng đếm trùng.

## 11. Thiết kế pointcut ghép theo quy trình có thể kiểm chứng

### Bước 1: Viết yêu cầu bằng lời trước

Ví dụ: “Ghi latency cho method có marker `@Observed` **hoặc** thuộc nhóm thao tác nhập dữ liệu, **ngoại trừ** method trong module logging nội bộ”.

Tách thành các mệnh đề:

```text
A = có marker Observed
B = thuộc nhóm import
C = thuộc module logging nội bộ

Kết quả cần: (A OR B) AND NOT C
```

Cách viết thành ngôn ngữ tự nhiên giúp tránh bỏ sót **phạm vi phủ định**.

### Bước 2: Chọn vũ trụ join point

Nêu rõ đang chọn **method execution** hay **method call** hoặc sự kiện khác. Xác nhận ngôn ngữ/công cụ hỗ trợ loại đó. Xác định liệu điểm mong muốn đi qua proxy, đã được weave hay thuộc cơ chế interception khác. Nếu không, dù Boolean đúng vẫn không có advice ở runtime.

### Bước 3: Chỉ rõ từng predicate

Mỗi mệnh đề cần một định nghĩa có thể kiểm tra:

- “Thuộc module import” có nghĩa gì: package, namespace, class, marker hay danh sách explicit?
- “Có marker” được kiểm tra ở declaration nào: interface, implementation hay inherited method?
- “Nội bộ” gồm cả generated code, logging helper và tác vụ background không?
- Có cần điều kiện runtime theo tham số, loại đối tượng hoặc request context không?

Định nghĩa mơ hồ tạo pointcut mơ hồ.

### Bước 4: Dùng dấu ngoặc thể hiện ý định

Viết đầy đủ `(A OR B) AND (NOT C)` thay vì `A OR B AND NOT C`. Với biểu thức dài, tách các nhóm con thành tên có nghĩa nếu DSL hoặc công cụ hỗ trợ; đừng nhân bản một điều kiện phức tạp khắp nơi.

### Bước 5: Dựng bảng ca kiểm thử tối thiểu

Một điểm cắt có OR và NOT thường cần ít nhất:

| A | B | C | Dự kiến |
| --- | --- | --- | --- |
| false | false | false | Loại vì không đạt nhánh dương. |
| true | false | false | Chọn nhờ A. |
| false | true | false | Chọn nhờ B. |
| true | true | false | Chọn; một pointcut Boolean đã khớp. |
| true | false | true | Loại vì C. |
| false | true | true | Loại vì C. |
| true | true | true | Loại vì C. |

Trường hợp `A=true, C=true` đặc biệt quan trọng vì dễ lộ lỗi dấu ngoặc.

### Bước 6: Kiểm chứng trên đường chạy thực tế

Chạy integration test qua cơ chế AOP thật. Gồm:

- **Positive:** điểm đúng phải nhận advice; ghi nhận lần và thứ tự phù hợp.
- **Negative:** điểm không thuộc rule không được tác động; đặc biệt các loại trừ.
- **Boundary:** overloaded/inherited method, marker tại interface hoặc implementation, lời gọi nội bộ, direct target, async.
- **Error path:** target ném lỗi; advice ghi nhận đúng nhưng không vô tình đổi exception.
- **Load:** tập điểm rộng có tạo logging quá nhiều hoặc overhead vượt ngân sách không?

Số dòng source khớp không chứng minh tần suất advice runtime; muốn đánh giá chi phí phải đo trên workload thực.

## 12. Những lỗi thường gặp khi dùng AND/OR/NOT

### 12.1. Quên ngoặc khi loại trừ

Sai mục tiêu:

```text
A OR B AND NOT C
```

Nếu ngữ nghĩa ưu tiên AND trước OR, nhánh A không bị loại bởi C. Viết:

```text
(A OR B) AND NOT C
```

để loại C khỏi **toàn bộ** tập được chọn.

### 12.2. Dùng OR thay AND

Muốn chọn “vừa nằm trong module thanh toán **vừa** có marker theo dõi” nhưng viết `A OR B` sẽ chọn cả các method chỉ thỏa một điều kiện. Đây là lỗi **mở rộng phạm vi**, có thể gây ảnh hưởng hệ thống nghiêm trọng nếu advice thay đổi hành vi.

### 12.3. Phủ định không có giới hạn dương

`NOT Internal` có thể chọn hầu như toàn bộ điểm khả dụng. Hãy có base rõ ràng, ví dụ `insideApiBoundary AND NOT Internal`.

### 12.4. Phủ định nhầm nhóm theo De Morgan

Muốn loại **cả hai loại** A và B nhưng viết `NOT A OR NOT B` là quá rộng. Đúng là `NOT (A OR B)`, tương đương `NOT A AND NOT B`.

### 12.5. Nhầm OR với hai advice độc lập

`A OR B` là một phép chọn tập, không phải chỉ dẫn chạy advice hai lần nếu cả A và B đúng. Nếu thực sự có hai aspect/advice độc lập, phân tích thứ tự và tần suất theo cấu hình riêng.

### 12.6. Tin rằng NOT “bắt” điểm chưa được engine hỗ trợ

Phủ định trên một predicate không biến field access, constructor hay self-invocation ngoài proxy thành sự kiện chặn được. **Join-point model và đường can thiệp là điều kiện tiên quyết.**

### 12.7. Cố ý tạo side effect trong predicate

Logic pointcut nên diễn tả tiêu chí; không nên dựa vào `A` được “chạy” trước `B` để cập nhật bộ đếm, mở tài nguyên hoặc quyết định nghiệp vụ. Cơ chế matcher có thể tối ưu, cache hoặc đánh giá theo phương pháp riêng.

### 12.8. Quá nhiều nhánh đặc biệt

Biểu thức `(A OR B OR C ...) AND NOT (X OR Y OR Z ...)` có thể khó hiểu, đặc biệt khi nhiều module cùng thêm quy tắc. Hãy định danh nhóm con, tài liệu hóa phạm vi, test riêng các nhánh và kiểm tra lại sau refactor. Không nên tăng độ phức tạp của pointcut chỉ để che giấu workflow nghiệp vụ.

## 13. Kiểm tra hiểu biết

**Câu 1.** A=true, B=false, C=true. Giá trị của `(A OR B) AND NOT C` và `A OR (B AND NOT C)` là gì?

**Đáp án:** Biểu thức thứ nhất false vì C loại toàn bộ; biểu thức thứ hai true vì A đã true.

**Câu 2.** Bạn muốn mọi điểm thuộc A hoặc B, trừ cả C và D. Chọn biểu thức nào?

```text
(A OR B) AND NOT (C OR D)
```

Biểu thức đó tương đương `(A OR B) AND NOT C AND NOT D` theo De Morgan.

**Câu 3.** Vì sao `A OR A` không làm một advice chạy hai lần?

**Đáp án:** Luật lũy đẳng: `A OR A` chọn cùng tập với A. Chạy nhiều advice hoặc lặp sự kiện runtime là câu chuyện khác.

**Câu 4.** Vì sao `NOT marker("Internal")` có thể nguy hiểm?

**Đáp án:** Nó chọn gần như mọi điểm trong vũ trụ công cụ quan sát được mà không có marker ấy; dễ ảnh hưởng quá nhiều chức năng và tạo overhead, logging dữ liệu không phù hợp.

**Câu 5.** Một method có marker phù hợp nhưng được gọi trực tiếp vào target, trong khi hệ thống chỉ dùng interface proxy. Advice có chắc chạy không?

**Đáp án:** Không. Cần đi qua proxy được cấu hình; Boolean match không tự tạo đường chặn.

**Câu 6.** Một method được gọi mười lần; nhánh điều kiện động A chỉ true trong bốn lượt, B false mọi lượt. Với `A OR B`, advice có thể chạy bao nhiêu lần?

**Đáp án:** Bốn nếu engine hỗ trợ matcher động, mọi lượt đi qua đường can thiệp và mỗi lượt khớp kích hoạt advice đúng một lần.

**Câu 7.** `callOf("save") AND executionOf("save")` có tự nhiên tương đương với “mọi save” không?

**Đáp án:** Không. Trong mô hình tách call/execution, hai loại join point có thể không cùng đúng trên một sự kiện. Phải chọn loại điểm phù hợp ý định.

## Kết luận

Kết hợp pointcut bằng **AND, OR, NOT** chính là bài toán **lấy giao, lấy hợp và loại trừ** trong một tập join point mà cơ chế AOP có thể quan sát. AND làm hẹp phạm vi; OR làm rộng phạm vi; NOT loại những sự kiện không mong muốn nhưng chỉ trong vũ trụ mà công cụ hỗ trợ. Dấu ngoặc giúp giữ đúng ý định, đặc biệt ở mẫu `(A OR B) AND NOT C`. Hãy luôn kiểm tra cả hai tầng: **logic chọn điểm có đúng không** và **đường thực thi có thật sự đi qua cơ chế can thiệp hay không**. Một pointcut ghép đáng tin là pointcut có bảng chân trị rõ, ca positive/negative và bằng chứng runtime xác thực.
