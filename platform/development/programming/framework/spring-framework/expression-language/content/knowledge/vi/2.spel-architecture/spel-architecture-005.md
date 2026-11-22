# PropertyAccessor, MethodResolver và ConstructorResolver trong SpEL

Trong Spring Expression Language (SpEL), ba strategy interface **PropertyAccessor**, **MethodResolver** và **ConstructorResolver** quyết định cách một biểu thức đọc/ghi thuộc tính, gọi phương thức và tạo đối tượng. Chúng được cung cấp thông qua **EvaluationContext**, vì vậy cùng một biểu thức có thể hoạt động với những quy tắc truy cập khác nhau tùy context được cấu hình.

## 1. Vị trí trong quá trình đánh giá biểu thức

SpEL phân tích chuỗi biểu thức thành cây cú pháp (AST), sau đó đánh giá các node của cây trong một EvaluationContext. Khi gặp một thao tác, node tương ứng hỏi các strategy trong context để tìm cách thực hiện:

| Cú pháp SpEL | Công việc | Strategy |
|---|---|---|
| `customer.address.city` | Đọc thuộc tính qua từng đối tượng | PropertyAccessor |
| `customer.rename('An')` | Tìm và gọi phương thức | MethodResolver |
| `new com.example.Customer('An')` | Tìm constructor phù hợp và tạo đối tượng | ConstructorResolver |

Ba interface này tách biệt việc **chọn cách truy cập** khỏi việc **thực thi thao tác**. MethodResolver trả về một MethodExecutor; ConstructorResolver trả về một ConstructorExecutor. PropertyAccessor tự cung cấp các thao tác kiểm tra, đọc và ghi.

Một số thành phần khác vẫn có vai trò riêng. Chẳng hạn, TypeLocator tìm lớp được nêu trong biểu thức; TypeConverter chuyển đổi kiểu giá trị; toán tử index như `items[0]` được xử lý bởi node index của SpEL. Không nên xem ba strategy trên là bộ xử lý cho mọi cú pháp của ngôn ngữ.

## 2. EvaluationContext quyết định strategy được sử dụng

EvaluationContext giữ root object và các dịch vụ cần thiết khi đánh giá biểu thức, trong đó có danh sách PropertyAccessor, MethodResolver và ConstructorResolver. Các strategy được thử theo thứ tự trong danh sách. Strategy phù hợp đầu tiên sẽ xử lý thao tác; nếu không có strategy nào đáp ứng, SpEL báo lỗi đánh giá.

Hai context thường gặp:

- **StandardEvaluationContext** cung cấp khả năng truy cập dựa trên reflection. Mặc định, nó có ReflectivePropertyAccessor, ReflectiveMethodResolver và ReflectiveConstructorResolver, cùng các dịch vụ như TypeConverter và TypeLocator.
- **SimpleEvaluationContext** dành cho trường hợp cần giới hạn tính năng. Context này không hỗ trợ type reference, constructor invocation, bean reference và phép gán. Việc gọi instance method phải được bật rõ ràng qua builder bằng `withInstanceMethods()`; property access cũng được chọn qua builder hoặc accessor do ứng dụng cung cấp.

Khi thay thế danh sách strategy, hãy giữ lại strategy mặc định nếu vẫn cần fallback reflection. Một custom accessor hoặc resolver quá rộng đặt trước có thể nhận những thao tác mà bạn muốn dành cho strategy khác.

## 3. PropertyAccessor: đọc và ghi thuộc tính

PropertyAccessor mô tả cách SpEL truy cập một thuộc tính có tên trên một target object. Interface nằm trong package `org.springframework.expression` và có các phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| `getSpecificTargetClasses()` | Khai báo các lớp target mà accessor chuyên xử lý; trả về `null` nếu không giới hạn theo lớp |
| `canRead(context, target, name)` | Cho biết có thể đọc thuộc tính hay không |
| `read(context, target, name)` | Đọc giá trị và trả về TypedValue |
| `canWrite(context, target, name)` | Cho biết có thể ghi thuộc tính hay không |
| `write(context, target, name, newValue)` | Ghi giá trị mới |

SpEL dùng `canRead` để tìm accessor có thể đọc thuộc tính, rồi gọi `read` trên accessor được chọn. Với phép gán, SpEL thực hiện quy trình tương tự bằng `canWrite` và `write`. Các phương thức có thể ném AccessException khi thao tác không thể thực hiện.

**TypedValue** mang giá trị đọc được cùng thông tin kiểu (TypeDescriptor). Khi kiểu tĩnh hoặc metadata kiểu có ý nghĩa đối với chuyển đổi dữ liệu, custom accessor nên trả về TypedValue với TypeDescriptor phù hợp thay vì chỉ dựa vào kiểu runtime.

### Accessor mặc định và trường hợp cần tùy biến

- **ReflectivePropertyAccessor** truy cập property theo JavaBean getter/setter và các field phù hợp thông qua reflection. Đây là accessor mặc định thường gặp trong StandardEvaluationContext.
- **DataBindingPropertyAccessor** phục vụ data binding với phạm vi truy cập được giới hạn hơn so với reflective accessor thông thường.
- Custom PropertyAccessor hữu ích khi dữ liệu có cấu trúc riêng, chẳng hạn thuộc tính ảo, cấu hình dạng Map hoặc một đối tượng proxy mà getter/setter JavaBean không mô tả đúng cách.

### Ví dụ: accessor cho Map

Ví dụ sau coi tên property là khóa trong Map. Phần import được lược bỏ để tập trung vào hợp đồng của interface.

    public final class MapPropertyAccessor implements PropertyAccessor {

        @Override
        public Class<?>[] getSpecificTargetClasses() {
            return new Class<?>[] { Map.class };
        }

        @Override
        public boolean canRead(
                EvaluationContext context, Object target, String name) {
            return target instanceof Map
                    && ((Map<?, ?>) target).containsKey(name);
        }

        @Override
        public TypedValue read(
                EvaluationContext context, Object target, String name)
                throws AccessException {
            Map<?, ?> map = (Map<?, ?>) target;
            if (!map.containsKey(name)) {
                throw new AccessException("No map entry named " + name);
            }
            return new TypedValue(map.get(name));
        }

        @Override
        public boolean canWrite(
                EvaluationContext context, Object target, String name) {
            return target instanceof Map;
        }

        @Override
        @SuppressWarnings("unchecked")
        public void write(
                EvaluationContext context, Object target,
                String name, Object newValue) throws AccessException {
            if (!(target instanceof Map)) {
                throw new AccessException("Target is not a Map");
            }
            ((Map<Object, Object>) target).put(name, newValue);
        }
    }

Nếu accessor này được đăng ký cho root Map, biểu thức `customer.name` có thể được diễn giải thành việc đọc khóa `customer` ở Map ngoài, rồi đọc khóa `name` ở Map lồng bên trong. Đây là quy ước do accessor định nghĩa; nó khác với cú pháp index `customer['name']`.

Một accessor tốt nên giới hạn target class bằng `getSpecificTargetClasses()` khi có thể. `canRead` và `canWrite` chỉ nên kiểm tra khả năng truy cập, không thực hiện thay đổi dữ liệu hoặc gọi dịch vụ có side effect. Nếu `canRead` trả về true nhưng `read` không thể hoàn thành, hãy ném AccessException với thông tin đủ để chẩn đoán.

## 4. MethodResolver: chọn phương thức cần gọi

MethodResolver chịu trách nhiệm tìm phương thức phù hợp với tên phương thức, target object và kiểu các đối số. Hợp đồng chính:

    MethodExecutor resolve(
        EvaluationContext context,
        Object targetObject,
        String name,
        List<TypeDescriptor> argumentTypes
    ) throws AccessException;

Resolver trả về MethodExecutor nếu tìm được cách gọi, hoặc `null` nếu không xử lý được lời gọi đó. MethodExecutor thực thi phương thức đã chọn:

    TypedValue execute(
        EvaluationContext context,
        Object target,
        Object... arguments
    ) throws AccessException;

**ReflectiveMethodResolver** là resolver mặc định trong StandardEvaluationContext. Nó tìm method phù hợp thông qua reflection, xét kiểu đối số và khả năng chuyển đổi kiểu. Việc phân giải có ý nghĩa đặc biệt khi lớp có nhiều overload, có tham số varargs hoặc khi đối số cần được chuyển đổi trước khi gọi.

Ví dụ, biểu thức:

    customer.rename('An')

yêu cầu resolver tìm method `rename` trên đối tượng customer với một đối số kiểu chuỗi. Resolver chọn một MethodExecutor; executor sau đó gọi method và trả kết quả dưới dạng TypedValue. Nếu biểu thức gọi method tĩnh qua type reference, target của lời gọi là đối tượng Class tương ứng; việc tìm lớp vẫn thuộc trách nhiệm của TypeLocator.

Bạn nên viết custom MethodResolver khi muốn biểu diễn một tập thao tác riêng, chuyển lời gọi sang service khác hoặc chỉ cho phép một allowlist method. Custom resolver cần xác định rõ tên method, target và kiểu đối số được chấp nhận; tránh cho phép gọi tùy ý mọi method công khai trên một đối tượng nhạy cảm.

## 5. ConstructorResolver: chọn constructor để tạo đối tượng

ConstructorResolver xử lý biểu thức tạo đối tượng bằng từ khóa `new`. Hợp đồng chính:

    ConstructorExecutor resolve(
        EvaluationContext context,
        String typeName,
        List<TypeDescriptor> argumentTypes
    ) throws AccessException;

Resolver trả về ConstructorExecutor phù hợp hoặc `null` nếu không xử lý được constructor đó. Executor thực hiện việc tạo đối tượng và trả về TypedValue:

    TypedValue execute(
        EvaluationContext context,
        Object... arguments
    ) throws AccessException;

**ReflectiveConstructorResolver** là resolver mặc định trong StandardEvaluationContext. Nó tìm constructor phù hợp bằng reflection và phối hợp với cơ chế chuyển đổi kiểu khi cần. TypeLocator chịu trách nhiệm tìm lớp từ tên lớp trong biểu thức; ConstructorResolver chịu trách nhiệm chọn constructor của lớp đã tìm được. Hai bước này là hai trách nhiệm khác nhau.

Ví dụ:

    new com.example.Customer('An')

SpEL tìm lớp Customer, sau đó tìm constructor nhận đối số phù hợp và tạo instance. Nếu không có constructor phù hợp, hoặc lớp không được tìm thấy, biểu thức sẽ thất bại với lỗi đánh giá tương ứng.

ConstructorResolver hữu ích khi ứng dụng cần một quy tắc khởi tạo riêng, chẳng hạn chỉ cho phép tạo một số kiểu đã định trước hoặc chuyển việc khởi tạo qua factory. Lời gọi static factory như `T(com.example.CustomerFactory).create('An')` là lời gọi method và đi qua cơ chế method resolution, không phải constructor resolution.

## 6. Đăng ký và sắp xếp strategy

Có thể cấu hình các strategy trên StandardEvaluationContext. Ví dụ sau đặt MapPropertyAccessor trước reflective accessor để Map được xử lý theo quy ước riêng, đồng thời vẫn giữ khả năng truy cập JavaBean cho các target khác:

    StandardEvaluationContext context =
            new StandardEvaluationContext(root);

    context.setPropertyAccessors(Arrays.asList(
            new MapPropertyAccessor(),
            new ReflectivePropertyAccessor()
    ));

    ExpressionParser parser = new SpelExpressionParser();
    Object result = parser.parseExpression("customer.name")
            .getValue(context);

Các danh sách method resolver và constructor resolver cũng được cấu hình tương tự bằng `setMethodResolvers(...)` và `setConstructorResolvers(...)`. Khi thay danh sách, hãy đưa custom resolver vào đúng vị trí ưu tiên và thêm lại ReflectiveMethodResolver hoặc ReflectiveConstructorResolver nếu muốn giữ fallback mặc định. Không thêm một resolver reflection thứ hai một cách máy móc nếu resolver mặc định đã đáp ứng nhu cầu.

Nếu chỉ cần truy cập property trong một luồng data binding, có thể dùng SimpleEvaluationContext với accessor phù hợp. Khi bật instance method bằng `withInstanceMethods()`, hãy xác định rõ những method nào có thể được gọi thông qua đối tượng được đưa vào context.

## 7. Chọn strategy và giới hạn quyền truy cập

| Nhu cầu | Hướng triển khai |
|---|---|
| Đọc/ghi JavaBean thông thường | Dùng ReflectivePropertyAccessor mặc định |
| Giới hạn property được phép truy cập | Dùng DataBindingPropertyAccessor hoặc custom PropertyAccessor |
| Truy cập dữ liệu dạng Map hoặc property ảo | Viết custom PropertyAccessor giới hạn target class |
| Gọi method thông thường và xử lý overload | Dùng ReflectiveMethodResolver |
| Chỉ cho phép một nhóm method | Viết custom MethodResolver theo allowlist |
| Tạo instance bằng constructor | Dùng ReflectiveConstructorResolver nếu context cho phép |
| Chỉ cho phép tạo một số kiểu | Viết custom ConstructorResolver hoặc giới hạn context |

Nếu biểu thức do người dùng nhập, hãy xem EvaluationContext là ranh giới quyền truy cập. StandardEvaluationContext cùng reflective accessor/resolver có thể mở ra nhiều khả năng đọc property, gọi method và tạo đối tượng. Hãy ưu tiên SimpleEvaluationContext khi tập tính năng hạn chế là đủ; chỉ đăng ký accessor hoặc resolver thật sự cần thiết. Không bật method invocation hoặc constructor invocation chỉ để tiện lợi nếu biểu thức không cần các khả năng đó.

Khi xây custom strategy, hãy giữ ba nguyên tắc:

1. **Giới hạn phạm vi:** chỉ nhận target class, property, method hoặc constructor mà ứng dụng dự định hỗ trợ.
2. **Tách kiểm tra khỏi thực thi:** các bước kiểm tra khả năng truy cập và phân giải không nên thay đổi trạng thái hệ thống.
3. **Giữ thông tin kiểu và lỗi rõ ràng:** trả TypedValue phù hợp, dùng AccessException cho lỗi ở tầng strategy và cung cấp thông điệp đủ cụ thể để xác định thao tác thất bại.

## 8. Ghi nhớ

PropertyAccessor quyết định cách đọc/ghi property; MethodResolver chọn cách gọi method; ConstructorResolver chọn cách tạo instance. Cả ba được cung cấp qua EvaluationContext và có thể được thay thế hoặc mở rộng để phù hợp với mô hình dữ liệu của ứng dụng. Khi cấu hình, thứ tự strategy, khả năng chuyển đổi kiểu và phạm vi quyền truy cập quyết định trực tiếp hành vi cũng như độ an toàn của biểu thức SpEL.
