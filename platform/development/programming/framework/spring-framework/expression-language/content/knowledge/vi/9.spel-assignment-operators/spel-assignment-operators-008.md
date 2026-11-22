# Chỉ cho phép gán khi hợp đồng ngữ cảnh xác nhận rõ trong SpEL

Spring Expression Language (SpEL) có thể đọc và ghi property của đối tượng. Vì vậy, một biểu thức có thể làm thay đổi trạng thái của object nếu EvaluationContext cung cấp quyền ghi phù hợp. Khi biểu thức đến từ cấu hình, người dùng hoặc một quy trình có thể thay đổi theo thời gian, việc cho phép gán phải dựa trên một hợp đồng rõ ràng: context nào được dùng, target nào được sửa, property nào được phép ghi và điều kiện nào phải thỏa mãn.

Không nên xem việc parser chấp nhận cú pháp gán là bằng chứng rằng thao tác đó được nghiệp vụ cho phép. Parser xử lý cú pháp; EvaluationContext và các PropertyAccessor quyết định cách truy cập dữ liệu; chính sách ứng dụng phải quyết định liệu lần ghi cụ thể có được ủy quyền hay không.

## 1. Hai cách ghi dữ liệu trong SpEL

SpEL có thể ghi property theo hai cách thường gặp:

**Dùng toán tử gán trong biểu thức:**

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("status = 'APPROVED'");
    expression.getValue(context);

Biểu thức này yêu cầu SpEL gán giá trị `'APPROVED'` vào property `status` của root object trong context. Việc gán chỉ thực hiện được nếu property accessor được cấu hình có thể ghi property đó.

**Dùng API setValue:**

    Expression property = parser.parseExpression("status");
    property.setValue(context, "APPROVED");

Ở đây biểu thức chỉ xác định đường dẫn property; ứng dụng gọi `setValue` để ghi giá trị vào đường dẫn đó. Đây là API ghi tường minh từ Java. Nó vẫn đi qua khả năng ghi của EvaluationContext và PropertyAccessor.

Hai cách trên đều có thể làm thay đổi object. Cần áp dụng cùng một chính sách quyền ghi cho cả hai đường đi, đặc biệt nếu ứng dụng cho phép nhiều thành phần sử dụng chung context.

## 2. PropertyAccessor là nơi thực hiện quyền ghi

EvaluationContext giữ danh sách PropertyAccessor. Mỗi accessor có thể xác định target class mà nó hỗ trợ, kiểm tra khả năng đọc/ghi và thực hiện thao tác tương ứng:

| Phương thức | Vai trò |
|---|---|
| `getSpecificTargetClasses()` | Khai báo các lớp target mà accessor hỗ trợ |
| `canRead(context, target, name)` | Kiểm tra khả năng đọc property |
| `read(context, target, name)` | Đọc giá trị property |
| `canWrite(context, target, name)` | Kiểm tra khả năng ghi property |
| `write(context, target, name, newValue)` | Thực hiện ghi giá trị |

Khi SpEL cần ghi một property, accessor phải xác nhận có thể ghi rồi thực hiện `write`. Với reflective accessor, khả năng ghi thường dựa trên setter hoặc field có thể truy cập. Nếu property chỉ có getter, hoặc accessor không hỗ trợ target/property đó, phép gán sẽ thất bại.

Cần phân biệt hai câu hỏi:

- **Có thể ghi không?** Đây là khả năng kỹ thuật mà `canWrite` kiểm tra.
- **Có được phép ghi không?** Đây là quyết định chính sách của ứng dụng dựa trên người gọi, target, property, trạng thái nghiệp vụ và mục đích của thao tác.

Một setter tồn tại không có nghĩa mọi người dùng biểu thức đều được phép gọi setter đó. Tương tự, `canWrite` trả về true không nên được dùng làm bằng chứng duy nhất cho quyền cập nhật.

## 3. Hợp đồng ngữ cảnh phải xác định điều gì?

Trước khi bật quyền ghi, ứng dụng nên xác định rõ hợp đồng cho EvaluationContext. Hợp đồng cần trả lời tối thiểu các câu hỏi sau:

1. **Ai được yêu cầu đánh giá biểu thức?** Xác định principal, vai trò hoặc quy trình đang thực hiện cập nhật.
2. **Đối tượng nào là target?** Chỉ rõ root object và phạm vi các object có thể truy cập từ root.
3. **Property nào được phép thay đổi?** Xác định allowlist property, hoặc nhóm property theo mục đích nghiệp vụ.
4. **Điều kiện nào phải đúng?** Ví dụ bản ghi còn ở trạng thái nháp, người dùng sở hữu bản ghi hoặc quy trình đã được phê duyệt.
5. **Kiểu giá trị nào được chấp nhận?** Xác định kiểu đích, quy tắc chuyển đổi, giới hạn và kiểm tra dữ liệu.
6. **Thay đổi được ghi nhận ra sao?** Xác định transaction, audit log, validation và xử lý lỗi cần thiết.

Hợp đồng này phải được kiểm tra ở phía ứng dụng trước khi tạo hoặc chọn context có quyền ghi. Không nên lấy một cờ do chính biểu thức nhập vào để tự cấp quyền cho biểu thức đó.

## 4. Mặc định chỉ đọc, mở quyền ghi theo nhu cầu

Với biểu thức chỉ dùng để lọc, hiển thị hoặc tính toán, nên chọn context chỉ đọc. SimpleEvaluationContext cung cấp builder dành cho data binding chỉ đọc:

    SimpleEvaluationContext readOnlyContext =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("status = 'APPROVED'");

Context chỉ đọc không cung cấp khả năng ghi property thông thường, nên biểu thức gán sẽ không thể hoàn tất thao tác ghi. Đây là cấu hình phù hợp khi biểu thức không cần cập nhật dữ liệu.

Khi use case đã được xác nhận cần cập nhật property theo data binding, có thể tạo context read-write:

    SimpleEvaluationContext writableContext =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

Chỉ chọn context read-write sau khi ứng dụng đã xác minh quyền của người gọi và mục tiêu cập nhật. Context này mở khả năng ghi cho những property mà accessor data binding hỗ trợ; nếu nghiệp vụ chỉ cho phép một tập property hẹp, cần thêm một accessor có chính sách allowlist hoặc một lớp kiểm soát tương đương.

SimpleEvaluationContext giới hạn nhiều khả năng của SpEL như type reference, constructor invocation và bean reference. Tuy nhiên, chọn SimpleEvaluationContext không tự động chứng minh rằng mọi property có thể ghi đều an toàn. Vẫn cần xác định rõ property và target được phép cập nhật.

## 5. Không dùng StandardEvaluationContext như một quyền ghi mặc định

StandardEvaluationContext cung cấp khả năng truy cập dựa trên reflection và mặc định có ReflectivePropertyAccessor. Điều đó thuận tiện cho các biểu thức nội bộ đáng tin cậy, nhưng có thể mở quyền đọc/ghi rộng hơn mức một use case cần.

Ví dụ, nếu root object là một đối tượng nghiệp vụ có nhiều setter, biểu thức có thể truy cập các property mà ứng dụng không định cho phép thay đổi trong luồng hiện tại. Việc một property có setter công khai không đồng nghĩa người dùng cuối được phép cập nhật nó qua SpEL.

Nếu phải dùng StandardEvaluationContext, hãy tạo context riêng cho mục đích cụ thể, kiểm soát root object, các accessor, method resolver và các dịch vụ khác được đăng ký. Không chia sẻ một context có quyền rộng giữa các biểu thức không cùng mức tin cậy. Đặc biệt, không để biểu thức do người dùng cung cấp tự do sử dụng các khả năng reflection, method invocation hoặc constructor invocation mà ứng dụng chưa cho phép.

## 6. Dùng allowlist cho property được phép ghi

Khi chỉ một số property được phép thay đổi, hãy thể hiện danh sách đó trong chính sách ứng dụng. Ví dụ, một luồng cập nhật đơn hàng có thể chỉ cho phép `note` và `deliveryComment`, trong khi các property như `id`, `owner`, `total` hoặc `paymentStatus` không được sửa qua biểu thức.

Một custom PropertyAccessor có thể kiểm tra target class và tên property:

    public final class PolicyPropertyAccessor implements PropertyAccessor {

        private final Set<String> writableProperties;

        public PolicyPropertyAccessor(Set<String> writableProperties) {
            this.writableProperties = Set.copyOf(writableProperties);
        }

        @Override
        public Class<?>[] getSpecificTargetClasses() {
            return new Class<?>[] { Order.class };
        }

        @Override
        public boolean canRead(
                EvaluationContext context, Object target, String name) {
            return target instanceof Order
                    && isReadableOrderProperty(name);
        }

        @Override
        public TypedValue read(
                EvaluationContext context, Object target, String name)
                throws AccessException {
            // Đọc property qua cơ chế được ứng dụng cho phép.
            return readAllowedProperty((Order) target, name);
        }

        @Override
        public boolean canWrite(
                EvaluationContext context, Object target, String name) {
            return target instanceof Order
                    && writableProperties.contains(name);
        }

        @Override
        public void write(
                EvaluationContext context, Object target,
                String name, Object newValue) throws AccessException {
            if (!(target instanceof Order)
                    || !writableProperties.contains(name)) {
                throw new AccessException("Property is not writable: " + name);
            }

            // Kiểm tra kiểu, giá trị và quy tắc nghiệp vụ trước khi ghi.
            writeValidatedProperty((Order) target, name, newValue);
        }
    }

Các hàm `isReadableOrderProperty`, `readAllowedProperty` và `writeValidatedProperty` trong ví dụ là phần xử lý do ứng dụng triển khai theo model thực tế; chúng không phải API có sẵn của Spring. Điểm chính là accessor phải kiểm tra cả target lẫn property, và `write` cần kiểm tra lại trước khi thay đổi dữ liệu.

Trong ứng dụng thực tế, policy thường cần thêm thông tin người gọi và trạng thái nghiệp vụ. Có thể truyền một policy object đã được xác thực vào accessor thay vì chỉ dùng một Set tên property. Không lấy allowlist từ nội dung biểu thức hoặc từ dữ liệu do người gọi không tin cậy tự khai báo.

## 7. Kiểm tra giá trị trước khi ghi

Được phép ghi một property vẫn chưa đủ để chấp nhận mọi giá trị. Trước khi gọi setter hoặc cập nhật field, hãy kiểm tra:

- Giá trị mới có thể chuyển đổi sang kiểu property đích không?
- Giá trị có nằm trong miền hợp lệ không, ví dụ độ dài chuỗi, giới hạn số hoặc tập trạng thái?
- Có cần kiểm tra quan hệ với các property khác không?
- Việc cập nhật có hợp lệ với trạng thái hiện tại của entity không?
- Setter có gây side effect hoặc kích hoạt thao tác bên ngoài không?

SpEL có thể sử dụng TypeConverter của EvaluationContext để chuyển giá trị sang kiểu đích trong các tình huống phù hợp. Chuyển đổi kiểu chỉ giải quyết khả năng biểu diễn dữ liệu; nó không thay thế validation nghiệp vụ.

Ví dụ, một chuỗi có thể chuyển thành số hợp lệ nhưng vẫn vượt giới hạn số lượng cho phép. Một trạng thái có thể đúng kiểu String nhưng không thuộc các trạng thái mà quy trình hiện tại chấp nhận. Hãy kiểm tra cả kiểu và ý nghĩa nghiệp vụ trước khi ghi.

## 8. Cô lập context theo từng mục đích

Không nên tạo một context read-write toàn cục rồi dùng lại cho mọi biểu thức. Hãy tạo context theo use case và target cụ thể:

- Biểu thức hiển thị hoặc lọc dữ liệu dùng context read-only.
- Biểu thức cập nhật chỉ dùng context có quyền ghi khi use case đã được xác thực.
- Các luồng cập nhật khác nhau có thể có allowlist property khác nhau.
- Không chia sẻ context giữa các request nếu root object, principal hoặc policy có thể thay đổi.

Một cách triển khai rõ ràng là có service tạo context:

    EvaluationContext createContext(
            User principal,
            Order order,
            UpdatePurpose purpose) {

        authorization.requireCanUpdate(principal, order, purpose);

        return buildContextFor(
                order,
                policyFor(principal, order, purpose)
        );
    }

Đây là cấu trúc minh họa: `authorization`, `UpdatePurpose`, `policyFor` và `buildContextFor` là thành phần ứng dụng tự xây dựng. Service phải xác minh quyền trước khi trả context có thể ghi.

Nếu biểu thức chỉ cần cập nhật một trường, có thể cân nhắc gọi setter hoặc service nghiệp vụ trực tiếp trong Java thay vì cho phép một biểu thức tổng quát sửa object. API chuyên biệt thường dễ kiểm soát quyền, validation và audit hơn.

## 9. Xử lý lỗi và ghi nhận thay đổi

Một phép gán có thể thất bại vì nhiều lý do: property không tồn tại, accessor không hỗ trợ ghi, property chỉ đọc, giá trị không chuyển đổi được, hoặc policy từ chối cập nhật. Hãy phân biệt lỗi cú pháp/phân tích biểu thức với lỗi đánh giá và lỗi nghiệp vụ.

Khi một lần gán được phép, ứng dụng nên kiểm tra kết quả và ghi nhận thay đổi theo yêu cầu của hệ thống. Với dữ liệu quan trọng, thao tác nên nằm trong transaction phù hợp để bảo đảm tính nhất quán nếu một bước validation hoặc persistence thất bại.

Không nên bắt lỗi rồi bỏ qua để tiếp tục như thể cập nhật thành công. Nếu policy từ chối, hãy trả lỗi rõ ràng cho tầng gọi và ghi log theo mức phù hợp. Tránh đưa dữ liệu nhạy cảm hoặc toàn bộ biểu thức chứa thông tin riêng tư vào log nếu không cần thiết.

## 10. Danh sách kiểm tra trước khi bật phép gán

Trước khi cho một biểu thức thực hiện assignment, hãy xác nhận:

1. Mục đích của biểu thức thực sự cần thay đổi trạng thái.
2. Người gọi được phép thực hiện use case cập nhật đó.
3. Root object và phạm vi object có thể truy cập đã được giới hạn.
4. Context được chọn có quyền ghi đúng mức cần thiết.
5. Property được ghi nằm trong allowlist của use case.
6. Giá trị mới được kiểm tra kiểu, miền giá trị và quy tắc nghiệp vụ.
7. Side effect, transaction và audit được xử lý rõ ràng.
8. Có kiểm thử cả trường hợp được phép lẫn bị từ chối.

## 11. Ghi nhớ

SpEL hỗ trợ assignment bằng toán tử `=` và API `Expression.setValue`; cả hai đều có thể làm thay đổi object thông qua PropertyAccessor. Hãy mặc định dùng context chỉ đọc cho biểu thức truy vấn. Chỉ tạo context có quyền ghi sau khi ứng dụng xác nhận rõ người gọi, target, property và mục đích cập nhật. Với các trường hợp chỉ cho phép sửa một số property, dùng allowlist được kiểm tra trong accessor và xác thực lại giá trị ngay trước khi ghi. Khả năng kỹ thuật ghi được một property không thay thế cho quyền nghiệp vụ được phép ghi property đó.
