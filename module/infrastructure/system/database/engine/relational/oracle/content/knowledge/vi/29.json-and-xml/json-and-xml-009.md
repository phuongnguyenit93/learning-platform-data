# PL/SQL JSON object type và thao tác cây JSON

Oracle cung cấp các kiểu object PL/SQL để đọc, tạo, duyệt và chỉnh sửa tài liệu JSON như một cây dữ liệu trong bộ nhớ. Bộ kiểu này thường được gọi là PL/SQL JSON DOM types. Các kiểu chính gồm:

- **JSON_ELEMENT_T**: kiểu cơ sở đại diện cho một phần tử JSON bất kỳ.
- **JSON_OBJECT_T**: đại diện cho một JSON object gồm các cặp key/value.
- **JSON_ARRAY_T**: đại diện cho một JSON array có thứ tự.
- **JSON_SCALAR_T**: đại diện cho giá trị scalar như string, number hoặc boolean.
- **JSON_KEY_LIST**: kiểu danh sách tên key được trả về khi lấy các key của object.

Các kiểu này cho phép PL/SQL parse JSON text thành cấu trúc có thể thao tác, đọc giá trị theo key hoặc index, thêm/xóa/thay đổi thuộc tính, chỉnh sửa object/array lồng nhau rồi serialize cây JSON trở lại VARCHAR2, CLOB hoặc BLOB.

Ví dụ, parse một object và cập nhật một thuộc tính:

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"orderId":1001,"status":"NEW","amount":250000}'
    );

    l_doc.put('status', 'APPROVED');

    DBMS_OUTPUT.PUT_LINE(l_doc.to_string());
END;
/
~~~

PL/SQL JSON object types phù hợp khi logic cần xử lý JSON theo từng nhánh hoặc thay đổi nhiều phần của tài liệu. Nếu mục tiêu chỉ là lọc, chiếu hoặc cập nhật dữ liệu JSON trong nhiều hàng, các hàm SQL/JSON như JSON_VALUE, JSON_QUERY, JSON_EXISTS, JSON_TABLE và JSON_TRANSFORM (tùy phiên bản) thường là lựa chọn tự nhiên hơn.

## 1. JSON như một cây dữ liệu

JSON có sáu dạng giá trị cơ bản:

- Object: tập hợp các cặp key/value.
- Array: danh sách giá trị có thứ tự.
- String: chuỗi ký tự.
- Number: số.
- Boolean: TRUE hoặc FALSE.
- Null: giá trị null của JSON.

Ví dụ:

~~~json
{
  "orderId": 1001,
  "customer": {
    "id": 25,
    "name": "An"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2,
      "price": 150000
    },
    {
      "sku": "MS-02",
      "quantity": 1,
      "price": 250000
    }
  ],
  "paid": false,
  "note": null
}
~~~

Cây trên có một object gốc. Thuộc tính customer chứa một object con; items chứa một array gồm hai object; paid là boolean; note là JSON null.

~~~text
root object
  orderId: number
  customer: object
    id: number
    name: string
  items: array
    [0]: object
      sku: string
      quantity: number
      price: number
    [1]: object
      sku: string
      quantity: number
      price: number
  paid: boolean
  note: null
~~~

### 1.1. Object và array khác nhau

Object truy cập phần tử bằng tên key:

~~~json
{"name":"An","age":30}
~~~

Array truy cập phần tử bằng vị trí:

~~~json
["An",30,true]
~~~

JSON array giữ thứ tự. JSON object là tập key/value; không nên dựa vào thứ tự key khi serialize hoặc duyệt object.

### 1.2. PL/SQL JSON types là cây trong bộ nhớ

Khi parse JSON text, Oracle tạo các object PL/SQL đại diện cho cây JSON. Thao tác PUT, APPEND hoặc REMOVE thay đổi cấu trúc trong bộ nhớ. Những thay đổi đó chưa tự ghi vào bảng; muốn lưu lại, phải serialize và thực hiện DML hoặc truyền kết quả về caller.

## 2. Các JSON object types

### 2.1. JSON_ELEMENT_T

JSON_ELEMENT_T là kiểu cơ sở cho một phần tử JSON. Nó có thể đại diện cho object, array hoặc scalar. Các phương thức kiểm tra kiểu thường dùng:

- IS_OBJECT
- IS_ARRAY
- IS_SCALAR
- IS_NULL
- IS_STRING
- IS_NUMBER
- IS_BOOLEAN
- GET_TYPE trên JSON_OBJECT_T/JSON_ARRAY_T: kiểu node theo key/index
- TO_STRING
- TO_CLOB
- TO_BLOB

Ví dụ:

~~~sql
DECLARE
    l_element JSON_ELEMENT_T;
BEGIN
    l_element := JSON_OBJECT_T.parse('{"active":true}');

    IF l_element.is_object() THEN
        DBMS_OUTPUT.PUT_LINE('Root is an object');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Root type is OBJECT');
END;
/
~~~

JSON_ELEMENT_T hữu ích khi chưa biết trước một node là object, array hay scalar.

### 2.2. JSON_OBJECT_T

JSON_OBJECT_T biểu diễn object. Các thao tác thường dùng:

- PARSE: phân tích JSON text thành object.
- GET: lấy một phần tử theo key dưới dạng JSON_ELEMENT_T.
- GET_STRING, GET_NUMBER, GET_BOOLEAN: lấy scalar theo kiểu mong muốn.
- GET_OBJECT, GET_ARRAY: lấy node con theo kiểu.
- HAS: kiểm tra key có tồn tại.
- GET_KEYS: lấy danh sách key.
- GET_SIZE: số thuộc tính.
- PUT: thêm hoặc thay thế key/value.
- PUT_NULL: gán JSON null.
- REMOVE: xóa key.
- RENAME_KEY: đổi tên key.
- TO_STRING, TO_CLOB, TO_BLOB: serialize object.

### 2.3. JSON_ARRAY_T

JSON_ARRAY_T biểu diễn array. Các thao tác thường dùng:

- PARSE: parse JSON array.
- GET và GET_STRING/GET_NUMBER/GET_BOOLEAN: lấy phần tử theo index.
- GET_OBJECT, GET_ARRAY: lấy object/array con.
- GET_SIZE: số phần tử.
- APPEND: thêm phần tử ở cuối.
- APPEND_NULL: thêm JSON null.
- PUT: chèn phần tử tại index; truyền OVERWRITE TRUE để thay phần tử đang có.
- PUT_NULL: đặt JSON null tại index.
- REMOVE: xóa phần tử theo index.
- TO_STRING, TO_CLOB, TO_BLOB: serialize array.

### 2.4. JSON_SCALAR_T

JSON_SCALAR_T đại diện cho giá trị scalar. Trong phần lớn code ứng dụng, có thể dùng trực tiếp các overload GET_STRING, GET_NUMBER, GET_BOOLEAN và PUT trên object/array thay vì phải tạo JSON_SCALAR_T thủ công.

### 2.5. JSON_KEY_LIST

GET_KEYS trả về danh sách tên key trong object. Kiểu kết quả là JSON_KEY_LIST, có thể duyệt như một collection PL/SQL:

~~~sql
DECLARE
    l_obj  JSON_OBJECT_T;
    l_keys JSON_KEY_LIST;
BEGIN
    l_obj := JSON_OBJECT_T.parse(
        '{"id":10,"name":"An","active":true}'
    );

    l_keys := l_obj.get_keys();

    FOR i IN 1 .. l_keys.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(l_keys(i));
    END LOOP;
END;
/
~~~

Thứ tự key được trả về không nên được xem là thứ tự nghiệp vụ. Nếu ứng dụng cần thứ tự hiển thị, hãy biểu diễn thứ tự đó bằng array hoặc một thuộc tính ordinal.

## 3. Parse JSON text

JSON_OBJECT_T và JSON_ARRAY_T có static method PARSE để chuyển JSON text thành object hoặc array tương ứng.

### 3.1. Parse root object

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"id":100,"name":"Oracle","enabled":true}'
    );

    DBMS_OUTPUT.PUT_LINE(l_doc.get_number('id'));
    DBMS_OUTPUT.PUT_LINE(l_doc.get_string('name'));
END;
/
~~~

Root JSON phải là object nếu dùng JSON_OBJECT_T.PARSE.

### 3.2. Parse root array

~~~sql
DECLARE
    l_values JSON_ARRAY_T;
BEGIN
    l_values := JSON_ARRAY_T.parse('[10,20,30]');

    DBMS_OUTPUT.PUT_LINE('Count=' || l_values.get_size());
    DBMS_OUTPUT.PUT_LINE('First=' || l_values.get_number(0));
END;
/
~~~

Root JSON phải là array nếu dùng JSON_ARRAY_T.PARSE.

### 3.3. Parse từ CLOB

Khi JSON document lớn hơn giới hạn VARCHAR2, lưu text vào CLOB và parse từ locator:

~~~sql
DECLARE
    l_json CLOB;
    l_doc  JSON_OBJECT_T;
BEGIN
    l_json := TO_CLOB(
        '{"documentId":10,"description":"A large document payload"}'
    );

    l_doc := JSON_OBJECT_T.parse(l_json);

    DBMS_OUTPUT.PUT_LINE(l_doc.get_number('documentId'));
END;
/
~~~

Trong ứng dụng thực tế, CLOB có thể được lấy từ cột bảng, request payload hoặc một API. Việc parse tạo cây object trong bộ nhớ, vì vậy tài liệu rất lớn vẫn tiêu thụ bộ nhớ session/PGA dù nguồn được lưu bằng CLOB.

### 3.4. JSON không hợp lệ hoặc sai root type

Nếu chuỗi không phải JSON hợp lệ, PARSE phát sinh lỗi. Nếu gọi JSON_OBJECT_T.PARSE cho một root array hoặc scalar, kiểu root không phù hợp. Hãy bắt lỗi parse tại ranh giới nhận dữ liệu:

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{invalid json}');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Cannot parse JSON');
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

Không nên bắt lỗi parse rồi âm thầm thay payload bằng object rỗng nếu điều đó khiến dữ liệu sai định dạng được coi là hợp lệ.

## 4. Tạo JSON object mới

Không cần parse text nếu muốn tạo cây JSON từ đầu. Có thể gọi constructor JSON_OBJECT_T().

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
BEGIN
    l_doc := JSON_OBJECT_T();

    l_doc.put('orderId', 1001);
    l_doc.put('status', 'NEW');
    l_doc.put('amount', 250000);
    l_doc.put('paid', FALSE);

    DBMS_OUTPUT.PUT_LINE(l_doc.to_string());
END;
/
~~~

PUT thêm key mới hoặc thay giá trị của key đã tồn tại.

### 4.1. PUT với scalar

~~~sql
l_doc.put('name', 'An');
l_doc.put('age', 30);
l_doc.put('active', TRUE);
l_doc.put('balance', 1250.75);
~~~

Datatype PL/SQL của actual argument xác định loại scalar JSON được tạo. Dùng BOOLEAN cho JSON boolean, NUMBER cho JSON number và VARCHAR2 cho JSON string.

### 4.2. Gán JSON null

Dùng PUT_NULL để biểu diễn JSON null:

~~~sql
l_doc.put_null('middleName');
~~~

Không nhầm JSON null với một key không tồn tại hoặc một PL/SQL variable đang NULL. Nếu cần thể hiện key có mặt nhưng không có giá trị, PUT_NULL là cách rõ ràng.

### 4.3. Thay giá trị key

~~~sql
l_doc.put('status', 'APPROVED');
~~~

Nếu status đã tồn tại, giá trị được thay thế. Nếu chưa tồn tại, key được thêm vào object.

### 4.4. Kiểm tra trước khi đọc

~~~sql
IF l_doc.has('status') THEN
    DBMS_OUTPUT.PUT_LINE(l_doc.get_string('status'));
ELSE
    DBMS_OUTPUT.PUT_LINE('status is missing');
END IF;
~~~

HAS kiểm tra sự tồn tại của key. Key JSON phân biệt chữ hoa/chữ thường, vì vậy status và Status là hai tên khác nhau.

## 5. Đọc giá trị từ JSON object

JSON_OBJECT_T có các getter theo datatype. Chọn getter phù hợp với kiểu JSON thực tế.

### 5.1. GET_STRING

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_name VARCHAR2(100);
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"name":"An"}');

    l_name := l_doc.get_string('name');

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

GET_STRING phù hợp khi giá trị là JSON string. Không dùng nó để đọc một object hoặc array.

### 5.2. GET_NUMBER

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_amount NUMBER;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"amount":1250.50}');

    l_amount := l_doc.get_number('amount');

    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

JSON number được ánh xạ sang NUMBER. Nếu ứng dụng cần precision/scale cụ thể, kiểm tra giới hạn nghiệp vụ trước khi ghi vào cột đích.

### 5.3. GET_BOOLEAN

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_active BOOLEAN;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"active":true}');

    l_active := l_doc.get_boolean('active');

    IF l_active THEN
        DBMS_OUTPUT.PUT_LINE('Active');
    END IF;
END;
/
~~~

JSON boolean không phải chuỗi 'true' hoặc 'false'. Dùng GET_BOOLEAN để lấy giá trị PL/SQL BOOLEAN.

### 5.4. GET_OBJECT và GET_ARRAY

~~~sql
DECLARE
    l_doc      JSON_OBJECT_T;
    l_customer JSON_OBJECT_T;
    l_items    JSON_ARRAY_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"customer":{"id":25,"name":"An"},"items":[1,2,3]}'
    );

    l_customer := l_doc.get_object('customer');
    l_items := l_doc.get_array('items');

    DBMS_OUTPUT.PUT_LINE(l_customer.get_string('name'));
    DBMS_OUTPUT.PUT_LINE(l_items.get_size());
END;
/
~~~

Dùng getter đúng kiểu node con. Nếu key không tồn tại hoặc giá trị không phải object/array, code cần xử lý trường hợp đó trước khi truy cập sâu hơn.

### 5.5. GET trả JSON_ELEMENT_T

Khi chưa biết kiểu của node:

~~~sql
DECLARE
    l_doc     JSON_OBJECT_T;
    l_element JSON_ELEMENT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse(
        '{"value":[1,2,3]}'
    );

    l_element := l_doc.get('value');

    IF l_element IS NOT NULL THEN
        DBMS_OUTPUT.PUT_LINE('Node type=' || l_doc.get_type('value'));

        IF l_element.is_array() THEN
            DBMS_OUTPUT.PUT_LINE('Value is an array');
        END IF;
    END IF;
END;
/
~~~

GET trả JSON_ELEMENT_T. Sau đó dùng IS_OBJECT, IS_ARRAY, IS_STRING, IS_NUMBER, IS_BOOLEAN hoặc IS_NULL để xác định cách đọc phù hợp.

### 5.6. Phân biệt missing key và JSON null

JSON có thể chứa:

~~~json
{"middleName":null}
~~~

Trong khi object khác có thể không có key middleName:

~~~json
{"firstName":"An"}
~~~

Hai trường hợp có ý nghĩa khác nhau:
- HAS('middleName') = FALSE: key không tồn tại.
- HAS('middleName') = TRUE và phần tử có IS_NULL = TRUE: key tồn tại với JSON null.

Ví dụ kiểm tra:

~~~sql
DECLARE
    l_doc     JSON_OBJECT_T;
    l_element JSON_ELEMENT_T;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"middleName":null}');

    IF l_doc.has('middleName') THEN
        l_element := l_doc.get('middleName');

        IF l_element.is_null() THEN
            DBMS_OUTPUT.PUT_LINE('Key exists with JSON null');
        END IF;
    ELSE
        DBMS_OUTPUT.PUT_LINE('Key is missing');
    END IF;
END;
/
~~~

Phân biệt này rất quan trọng khi API dùng PATCH: key bị bỏ qua có thể có nghĩa “không thay đổi”, còn key có JSON null có thể có nghĩa “xóa giá trị”.

## 6. Reference semantics, value semantics và CLONE

Khi lấy node con, cần hiểu biến nhận được là bản sao hay tham chiếu tới node nằm trong cây gốc. Đây là điểm quan trọng khi sửa JSON lồng nhau.

### 6.1. GET trả tham chiếu tới node phức hợp

Phương thức GET trả JSON_ELEMENT_T tham chiếu tới node trong object/array nguồn. Nếu node là object hoặc array và bạn sửa node đó, thay đổi được phản ánh trong cây cha.

~~~sql
DECLARE
    l_root    JSON_OBJECT_T;
    l_address JSON_OBJECT_T;
BEGIN
    l_root := JSON_OBJECT_T.parse(
        '{"name":"An","address":{"city":"Hanoi"}}'
    );

    l_address := l_root.get_object('address');
    l_address.put('city', 'Ho Chi Minh City');
    l_address.put('district', 'District 1');

    -- Các thay đổi trên l_address đã nằm trong l_root.
    DBMS_OUTPUT.PUT_LINE(l_root.to_string());
END;
/
~~~

Không cần PUT lại address chỉ để đưa các thay đổi của node tham chiếu trở về object cha. PUT lại cùng node có thể làm code khó hiểu và không cần thiết.

### 6.2. Getter scalar trả giá trị độc lập

GET_STRING, GET_NUMBER và GET_BOOLEAN trả giá trị scalar theo value semantics. Thay đổi biến PL/SQL nhận kết quả không sửa node JSON:

~~~sql
DECLARE
    l_doc   JSON_OBJECT_T;
    l_value NUMBER;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"amount":100}');

    l_value := l_doc.get_number('amount');
    l_value := 500;

    -- amount trong l_doc vẫn là 100.
    DBMS_OUTPUT.PUT_LINE(l_doc.to_string());
END;
/
~~~

Nếu muốn thay scalar trong cây, gọi PUT trên object hoặc PUT trên array.

### 6.3. CLONE tạo bản sao sâu

CLONE tạo một bản sao độc lập của object hoặc array. Thay đổi trên bản clone không làm thay đổi cây ban đầu:

~~~sql
DECLARE
    l_root       JSON_OBJECT_T;
    l_address    JSON_OBJECT_T;
    l_copy       JSON_OBJECT_T;
BEGIN
    l_root := JSON_OBJECT_T.parse(
        '{"address":{"city":"Hanoi"}}'
    );

    l_address := l_root.get_object('address');
    l_copy := l_address.clone();

    l_copy.put('city', 'Da Nang');

    DBMS_OUTPUT.PUT_LINE('Original=' || l_root.to_string());
    DBMS_OUTPUT.PUT_LINE('Copy=' || l_copy.to_string());
END;
/
~~~

Dùng CLONE khi cần tạo nhánh xử lý độc lập, giữ snapshot trước khi chỉnh sửa hoặc truyền object cho routine không được phép thay đổi cây gốc.

### 6.4. TREAT chuyển JSON_ELEMENT_T sang subtype

GET trả JSON_ELEMENT_T. Khi đã kiểm tra node là object hoặc array, có thể dùng TREAT để chuyển sang kiểu cụ thể:

~~~sql
DECLARE
    l_root    JSON_ELEMENT_T;
    l_object  JSON_OBJECT_T;
    l_element JSON_ELEMENT_T;
BEGIN
    l_root := JSON_ELEMENT_T.parse('{"items":[1,2]}');

    IF l_root.is_object() THEN
        l_object := TREAT(l_root AS JSON_OBJECT_T);
        l_element := l_object.get('items');

        IF l_element.is_array() THEN
            DBMS_OUTPUT.PUT_LINE('items is an array');
        END IF;
    END IF;
END;
/
~~~

Chỉ TREAT sau khi kiểm tra kiểu. Ép một scalar thành JSON_OBJECT_T không biến scalar thành object hợp lệ.

## 7. JSON_ARRAY_T: index, PUT và REMOVE

JSON_ARRAY_T có thứ tự và index bắt đầu từ 0. Ngoài APPEND, cần hiểu chính xác semantics của PUT.

### 7.1. PUT mặc định chèn phần tử

Khi index đã tồn tại, PUT mặc định chèn phần tử mới tại vị trí đó và đẩy các phần tử từ vị trí đó trở về sau sang phải:

~~~sql
DECLARE
    l_array JSON_ARRAY_T;
BEGIN
    l_array := JSON_ARRAY_T.parse('["A","B","C"]');

    l_array.put(1, 'X');

    DBMS_OUTPUT.PUT_LINE(l_array.to_string());
END;
/
~~~

Kết quả có thứ tự A, X, B, C. Vì vậy PUT không mặc định có nghĩa là ghi đè.

### 7.2. PUT với OVERWRITE TRUE để thay phần tử

Nếu muốn thay giá trị tại một index mà không dịch chuyển phần tử khác, truyền TRUE cho tham số OVERWRITE:

~~~sql
l_array.put(1, 'X', TRUE);
~~~

Với array ban đầu ["A","B","C"], kết quả là ["A","X","C"].

Dùng APPEND khi muốn thêm ở cuối; dùng PUT(index, value, TRUE) khi muốn thay phần tử tại vị trí hiện tại; dùng PUT mặc định khi thực sự muốn chèn.

### 7.3. PUT_NULL cũng có tham số OVERWRITE

~~~sql
l_array.put_null(1, TRUE);
~~~

Câu lệnh thay phần tử index 1 bằng JSON null. Nếu bỏ TRUE và index đang tồn tại, PUT_NULL có thể chèn một phần tử null và dịch chuyển các phần tử sau.

### 7.4. REMOVE làm thay đổi index của các phần tử sau

~~~sql
DECLARE
    l_array JSON_ARRAY_T;
BEGIN
    l_array := JSON_ARRAY_T.parse('["A","B","C","D"]');
    l_array.remove(1);

    DBMS_OUTPUT.PUT_LINE(l_array.to_string());
END;
/
~~~

Sau khi xóa index 1, array trở thành ["A","C","D"]. Phần tử C chuyển từ index 2 sang index 1; D chuyển từ index 3 sang index 2.

Không lưu index lâu dài nếu array có thể được chèn hoặc xóa. Nếu cần định danh ổn định, mỗi object trong array nên có thuộc tính ID riêng.

### 7.5. Thay phần tử object bằng reference semantics

Nếu lấy object con bằng GET_OBJECT rồi sửa trực tiếp, thay đổi được phản ánh trong array:

~~~sql
DECLARE
    l_items JSON_ARRAY_T;
    l_item  JSON_OBJECT_T;
BEGIN
    l_items := JSON_ARRAY_T.parse(
        '[{"sku":"KB-01","quantity":2},{"sku":"MS-02","quantity":1}]'
    );

    l_item := l_items.get_object(0);
    l_item.put('quantity', 3);

    DBMS_OUTPUT.PUT_LINE(l_items.to_string());
END;
/
~~~

Nếu chủ động CLONE object trước khi sửa, dùng PUT với OVERWRITE TRUE để thay phần tử cũ:

~~~sql
l_item := l_items.get_object(0).clone();
l_item.put('quantity', 3);
l_items.put(0, l_item, TRUE);
~~~

Nếu bỏ TRUE ở ví dụ cuối, Oracle sẽ chèn object mới tại index 0 và dịch object cũ sang index 1.

## 8. Thao tác object và array lồng nhau

Các document thực tế thường có nhiều tầng. Cách tiếp cận dễ kiểm soát là đi từng node, kiểm tra kiểu, rồi thực hiện thay đổi tại đúng container.

### 8.1. Thêm object lồng nhau

~~~sql
DECLARE
    l_root    JSON_OBJECT_T;
    l_profile JSON_OBJECT_T;
    l_contact JSON_OBJECT_T;
BEGIN
    l_root := JSON_OBJECT_T();

    l_profile := JSON_OBJECT_T();
    l_profile.put('displayName', 'An');

    l_contact := JSON_OBJECT_T();
    l_contact.put('email', 'an@example.com');
    l_contact.put('phone', '0900000000');

    l_profile.put('contact', l_contact);
    l_root.put('profile', l_profile);

    DBMS_OUTPUT.PUT_LINE(l_root.to_string());
END;
/
~~~

PUT nhận JSON_ELEMENT_T hoặc các subtype tương ứng, nên có thể gắn object/array con vào container cha.

### 8.2. Thêm array vào object

~~~sql
DECLARE
    l_root  JSON_OBJECT_T;
    l_roles JSON_ARRAY_T;
BEGIN
    l_root := JSON_OBJECT_T();
    l_roles := JSON_ARRAY_T();

    l_roles.append('READER');
    l_roles.append('EDITOR');

    l_root.put('roles', l_roles);

    DBMS_OUTPUT.PUT_LINE(l_root.to_string());
END;
/
~~~

### 8.3. Tìm phần tử trong array theo thuộc tính

JSON_ARRAY_T không có key nghiệp vụ tự động. Muốn tìm item theo SKU, duyệt các object:

~~~sql
DECLARE
    l_items JSON_ARRAY_T;
    l_item  JSON_OBJECT_T;
    l_found PLS_INTEGER := NULL;
BEGIN
    l_items := JSON_ARRAY_T.parse(
        '[{"sku":"KB-01"},{"sku":"MS-02"},{"sku":"HD-03"}]'
    );

    IF l_items.get_size() > 0 THEN
        FOR i IN 0 .. l_items.get_size() - 1 LOOP
            l_item := l_items.get_object(i);

            IF l_item.has('sku')
               AND l_item.get_string('sku') = 'MS-02'
            THEN
                l_found := i;
                EXIT;
            END IF;
        END LOOP;
    END IF;

    IF l_found IS NOT NULL THEN
        DBMS_OUTPUT.PUT_LINE('Found at index ' || l_found);
    END IF;
END;
/
~~~

Với array rất lớn và cần truy vấn theo key thường xuyên, cân nhắc chuyển dữ liệu thành bảng quan hệ hoặc dùng JSON_TABLE thay vì quét cây nhiều lần.

### 8.4. Xóa item theo SKU

~~~sql
IF l_found IS NOT NULL THEN
    l_items.remove(l_found);
END IF;
~~~

Sau REMOVE, các index phía sau thay đổi. Nếu xóa nhiều phần tử khi duyệt, duyệt từ cuối về đầu hoặc tính lại index sau mỗi lần xóa để tránh bỏ sót.

## 9. ON_ERROR: kiểm soát cách JSON DOM báo lỗi

Các JSON object types có phương thức ON_ERROR để chọn hành vi khi thao tác JSON gặp lỗi, ví dụ key không tồn tại, datatype không khớp hoặc array index không hợp lệ.

Mặc định, JSON DOM có thể trả PL/SQL NULL thay vì ném exception cho một số lỗi thao tác. Điều này có thể khiến lỗi dữ liệu bị hiểu nhầm là giá trị null. Có thể đặt chính sách rõ ràng:

~~~sql
l_doc.on_error(1);
~~~

Các giá trị thường dùng:

| Giá trị | Hành vi |
| ---: | --- |
| 0 | Hành vi mặc định: trả NULL cho lỗi theo chính sách mặc định |
| 1 | Ném exception cho mọi lỗi |
| 2 | Ném exception khi không tìm thấy giá trị |
| 3 | Ném exception khi datatype không phù hợp |
| 4 | Ném exception khi input không hợp lệ, ví dụ index array ngoài phạm vi |
| 7 | Kết hợp 3 và 4 |

ON_ERROR được đặt trên một JSON_ELEMENT_T instance và áp dụng cho các thao tác tiếp theo qua instance đó. Có thể gọi ON_ERROR(0) để trở lại hành vi mặc định.

### 9.1. Bật strict error handling

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_amount NUMBER;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"amount":"not-a-number"}');
    l_doc.on_error(1);

    l_amount := l_doc.get_number('amount');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

Với strict handling, lỗi chuyển đổi được ném ra để caller xử lý. Đây thường là lựa chọn dễ chẩn đoán khi nhận JSON từ client không tin cậy.

### 9.2. Kiểm tra missing key trước getter

~~~sql
IF NOT l_doc.has('customerId') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Missing customerId');
END IF;

l_customer_id := l_doc.get_number('customerId');
~~~

HAS giúp phân biệt key thiếu. ON_ERROR giúp quy định cách xử lý các lỗi còn lại như type mismatch hoặc index invalid.

### 9.3. GET_STRING có thể chuyển đổi kiểu

Một số getter có thể thực hiện chuyển đổi nếu có thể. Ví dụ GET_STRING có thể trả biểu diễn chuỗi của một giá trị không phải JSON string. Vì vậy, nếu hợp đồng yêu cầu đúng kiểu JSON string, hãy kiểm tra IS_STRING hoặc GET_TYPE trước khi gọi GET_STRING.

~~~sql
l_element := l_doc.get('status');

IF l_element IS NULL OR NOT l_element.is_string() THEN
    RAISE_APPLICATION_ERROR(-20002, 'status must be a JSON string');
END IF;

l_status := l_doc.get_string('status');
~~~

Không dựa vào việc getter chuyển đổi được để bỏ qua validation schema.

## 10. JSON null, SQL NULL và missing key

Ba trạng thái thường bị nhầm:

| Trạng thái | Ví dụ | Cách nhận biết |
| --- | --- | --- |
| Key không tồn tại | {} | HAS(key) = FALSE |
| Key có JSON null | {"note":null} | HAS(key) = TRUE và node IS_NULL |
| PL/SQL NULL | Biến/locator chưa có instance | Biến PL/SQL IS NULL |

JSON null là một node hợp lệ trong cây JSON. Nó không giống PL/SQL NULL và cũng không giống key vắng mặt.

### 10.1. Quy tắc cho API PATCH

Một API PATCH thường cần phân biệt:
- Không gửi key: không thay đổi thuộc tính hiện tại.
- Gửi key với giá trị null: xóa hoặc đặt null theo hợp đồng API.
- Gửi key với giá trị mới: cập nhật thuộc tính.

Ví dụ:

~~~sql
IF l_patch.has('middleName') THEN
    l_value := l_patch.get('middleName');

    IF l_value.is_null() THEN
        l_target.remove('middleName');
    ELSE
        l_target.put('middleName', l_value);
    END IF;
END IF;
~~~

Đoạn code thể hiện một chính sách cụ thể: JSON null được hiểu là xóa key. Nếu nghiệp vụ muốn giữ key với JSON null, dùng PUT_NULL thay cho REMOVE.

### 10.2. SQL NULL của toàn document

Nếu cột CLOB payload là SQL NULL, không có JSON text để parse. Kiểm tra NULL trước khi gọi PARSE:

~~~sql
IF l_payload IS NULL THEN
    RAISE_APPLICATION_ERROR(-20003, 'JSON payload is NULL');
END IF;
~~~

Không thay SQL NULL bằng object rỗng một cách tự động trừ khi đó là quy tắc dữ liệu đã được thống nhất.

## 11. Serialize JSON: VARCHAR2, CLOB và BLOB

Sau khi chỉnh sửa cây, serialize để nhận JSON text.

### 11.1. TO_STRING cho document nhỏ

~~~sql
DECLARE
    l_doc JSON_OBJECT_T;
    l_text VARCHAR2(32767);
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"id":10,"status":"NEW"}');
    l_doc.put('status', 'DONE');

    l_text := l_doc.to_string();
    DBMS_OUTPUT.PUT_LINE(l_text);
END;
/
~~~

TO_STRING trả VARCHAR2. Dùng cho payload nhỏ; không dùng nếu document có thể vượt giới hạn VARCHAR2 trong PL/SQL.

### 11.2. TO_CLOB cho document lớn

~~~sql
DECLARE
    l_doc  JSON_OBJECT_T;
    l_json CLOB;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"id":10,"status":"NEW"}');
    l_doc.put('status', 'DONE');

    l_json := l_doc.to_clob();

    DBMS_OUTPUT.PUT_LINE(
        'Length=' || DBMS_LOB.GETLENGTH(l_json)
    );

    IF DBMS_LOB.ISTEMPORARY(l_json) = 1 THEN
        DBMS_LOB.FREETEMPORARY(l_json);
    END IF;
END;
/
~~~

Dạng function TO_CLOB không tham số tạo temporary CLOB làm đích serialize. Kiểm tra ISTEMPORARY và giải phóng khi không còn cần.

### 11.3. TO_CLOB với locator đích do caller cấp

Có dạng member procedure nhận CLOB IN OUT để caller cung cấp LOB đích. Locator đích phải được khởi tạo hợp lệ, không phải PL/SQL NULL:

~~~sql
DECLARE
    l_doc    JSON_OBJECT_T;
    l_output CLOB;
BEGIN
    l_doc := JSON_OBJECT_T.parse('{"id":10,"status":"DONE"}');

    DBMS_LOB.CREATETEMPORARY(l_output, TRUE, DBMS_LOB.CALL);
    l_doc.to_clob(l_output);

    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.GETLENGTH(l_output));

    DBMS_LOB.FREETEMPORARY(l_output);
END;
/
~~~

Cách này hữu ích khi caller muốn kiểm soát locator đích hoặc tái sử dụng một LOB đã tạo.

### 11.4. TO_BLOB và UTF-8

TO_BLOB serialize JSON text dưới dạng BLOB với UTF-8. Đây là lựa chọn phù hợp khi tầng tích hợp yêu cầu byte payload. Khi chuyển đổi sang hệ thống khác, thống nhất encoding để tránh lỗi ký tự tiếng Việt hoặc ký tự ngoài ASCII.

### 11.5. Pretty output và compact output

Pretty output thêm khoảng trắng và xuống dòng để dễ đọc. Compact output thường nhỏ hơn và phù hợp truyền tải. Không dựa vào thứ tự key hoặc cách xuống dòng khi so sánh hai JSON object; nếu cần kiểm tra tương đương, so sánh cấu trúc hoặc chuẩn hóa theo quy tắc của ứng dụng.

## 12. Lưu JSON vào database

Các instance JSON_OBJECT_T/JSON_ARRAY_T là object trong bộ nhớ PL/SQL. Chúng không tự trở thành một hàng dữ liệu persistent. Cần serialize hoặc chuyển sang kiểu JSON SQL được hỗ trợ rồi thực hiện DML.

### 12.1. Bảng dùng CLOB và IS JSON

~~~sql
CREATE TABLE json_document_store (
    document_id NUMBER PRIMARY KEY,
    payload     CLOB,
    CONSTRAINT json_document_store_ck
        CHECK (payload IS JSON)
);
~~~

IS JSON constraint đảm bảo nội dung CLOB thỏa cú pháp JSON khi INSERT/UPDATE từ các client khác nhau.

### 12.2. Parse, chỉnh sửa và UPDATE

~~~sql
DECLARE
    l_payload CLOB;
    l_doc     JSON_OBJECT_T;
    l_output  CLOB;
BEGIN
    SELECT payload
    INTO l_payload
    FROM json_document_store
    WHERE document_id = 1
    FOR UPDATE;

    l_doc := JSON_OBJECT_T.parse(l_payload);
    l_doc.on_error(1);

    l_doc.put('status', 'APPROVED');
    l_doc.put('approvedBy', 'APP_USER');

    l_output := l_doc.to_clob();

    UPDATE json_document_store
    SET payload = l_output
    WHERE document_id = 1;

    COMMIT;

    IF l_output IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_output) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_output);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF l_output IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_output) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_output);
        END IF;

        ROLLBACK;
        RAISE;
END;
/
~~~

SELECT FOR UPDATE khóa hàng trong transaction để tránh hai session đồng thời đọc cùng document rồi ghi đè thay đổi của nhau. Trong ứng dụng thật, transaction boundary thường thuộc caller hoặc service layer; COMMIT trong block chỉ là minh họa.

### 12.3. Native JSON data type

Các phiên bản Oracle hiện đại có native SQL JSON data type. Khả năng cụ thể phụ thuộc phiên bản database và compatibility setting. Khi dùng native JSON, có thể chuyển giữa JSON DOM object types và SQL JSON data bằng các API hỗ trợ như TO_JSON/constructor tương ứng ở phiên bản có cung cấp.

Nếu dùng textual storage CLOB/BLOB, serialize JSON thành text rồi ghi vào cột. Không giả định một JSON_OBJECT_T instance có thể được lưu trực tiếp như một biến PL/SQL.

### 12.4. Kiểm tra sau khi lưu

~~~sql
SELECT document_id,
       JSON_VALUE(payload, '$.status') AS status,
       JSON_VALUE(payload, '$.approvedBy') AS approved_by
FROM json_document_store
WHERE document_id = 1;
~~~

Dùng SQL/JSON để xác nhận các thuộc tính đã được lưu. Đây cũng là cách để các ứng dụng SQL khác đọc dữ liệu JSON mà không cần gọi PL/SQL DOM.

## 13. Kết hợp với SQL/JSON

PL/SQL JSON DOM và SQL/JSON giải quyết các nhu cầu khác nhau.

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Chỉnh sửa nhiều node theo điều kiện procedural | JSON_OBJECT_T / JSON_ARRAY_T |
| Duyệt đệ quy cây JSON | JSON_ELEMENT_T và subtype |
| Lấy một scalar từ nhiều hàng | JSON_VALUE |
| Lấy fragment JSON | JSON_QUERY |
| Kiểm tra path tồn tại | JSON_EXISTS |
| Chuyển array/object thành hàng quan hệ | JSON_TABLE |
| Tạo JSON từ cột SQL | JSON_OBJECT / JSON_ARRAY |
| Cập nhật JSON theo path trong SQL | JSON_TRANSFORM khi phiên bản hỗ trợ |

### 13.1. JSON_VALUE

~~~sql
SELECT document_id,
       JSON_VALUE(payload, '$.customer.name') AS customer_name
FROM json_document_store;
~~~

JSON_VALUE trích một scalar theo path. Nếu chỉ cần một vài thuộc tính từ nhiều hàng, thường không cần parse toàn bộ document thành DOM trong từng vòng lặp PL/SQL.

### 13.2. JSON_QUERY

~~~sql
SELECT JSON_QUERY(payload, '$.customer')
FROM json_document_store;
~~~

JSON_QUERY trả một object/array fragment theo path.

### 13.3. JSON_EXISTS

~~~sql
SELECT document_id
FROM json_document_store
WHERE JSON_EXISTS(payload, '$.items[*]?(@.quantity > 1)');
~~~

JSON_EXISTS kiểm tra path có khớp dữ liệu hay không. Cú pháp filter path cần tương thích phiên bản Oracle.

### 13.4. JSON_TABLE

~~~sql
SELECT d.document_id,
       jt.sku,
       jt.quantity
FROM json_document_store d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             sku      VARCHAR2(30) PATH '$.sku',
             quantity NUMBER       PATH '$.quantity'
         )
     ) jt;
~~~

JSON_TABLE biến từng item thành một hàng quan hệ. Với truy vấn set-based trên nhiều document, cách này thường rõ ràng và hiệu quả hơn vòng lặp PL/SQL parse từng document.

## 14. Validation và bảo vệ dữ liệu đầu vào

PARSE kiểm tra cú pháp JSON, không kiểm tra toàn bộ schema hay quy tắc nghiệp vụ.

### 14.1. Kiểm tra key bắt buộc

~~~sql
IF NOT l_doc.has('orderId') THEN
    RAISE_APPLICATION_ERROR(-20010, 'Missing orderId');
END IF;
~~~

### 14.2. Kiểm tra kiểu JSON

~~~sql
l_element := l_doc.get('amount');

IF l_element IS NULL OR NOT l_element.is_number() THEN
    RAISE_APPLICATION_ERROR(-20011, 'amount must be a number');
END IF;

l_amount := l_doc.get_number('amount');
~~~

Kiểm tra kiểu trước getter giúp tránh tự động chuyển đổi không mong muốn.

### 14.3. Kiểm tra range nghiệp vụ

~~~sql
IF l_amount <= 0 OR l_amount > 1000000000 THEN
    RAISE_APPLICATION_ERROR(-20012, 'amount is outside allowed range');
END IF;
~~~

Một giá trị có kiểu NUMBER vẫn có thể không hợp lệ về nghiệp vụ.

### 14.4. Kiểm tra array và từng phần tử

~~~sql
IF NOT l_doc.has('items') THEN
    RAISE_APPLICATION_ERROR(-20013, 'Missing items');
END IF;

l_element := l_doc.get('items');

IF NOT l_element.is_array() THEN
    RAISE_APPLICATION_ERROR(-20014, 'items must be an array');
END IF;

l_items := l_doc.get_array('items');

IF l_items.get_size() = 0 THEN
    RAISE_APPLICATION_ERROR(-20015, 'items cannot be empty');
END IF;
~~~

Sau đó duyệt từng item, xác nhận nó là object và có các key bắt buộc như sku, quantity, price.

### 14.5. Giới hạn payload

Với JSON nhận từ client:
- Giới hạn kích thước payload.
- Giới hạn độ sâu lồng nhau.
- Giới hạn số phần tử array.
- Xác thực datatype và range.
- Không log toàn bộ payload nếu có thông tin cá nhân hoặc bí mật.
- Không dùng JSON key/value trực tiếp làm dynamic SQL identifier nếu chưa kiểm soát.

## 15. Ngày và thời gian trong JSON

JSON chuẩn không có datatype DATE hoặc TIMESTAMP riêng. Ngày giờ thường được biểu diễn bằng string theo ISO 8601, ví dụ:

~~~json
{"createdAt":"2026-11-14T10:30:00+00:00"}
~~~

Nếu parse text JSON như trên, createdAt là JSON string. Dùng GET_STRING rồi chuyển bằng TO_TIMESTAMP_TZ với format model rõ ràng:

~~~sql
l_text := l_doc.get_string('createdAt');

l_created_at := TO_TIMESTAMP_TZ(
    l_text,
    'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM'
);
~~~

Các PL/SQL JSON types cũng có overload nhận DATE/TIMESTAMP khi tạo scalar trong bộ nhớ; khi serialize, giá trị được biểu diễn theo dạng chuỗi ISO 8601. Nhưng sau khi parse một JSON text thông thường, chuỗi ngày vẫn là string, không tự biến thành SQL DATE.

Thống nhất timezone và format giữa producer/consumer. Không dựa vào NLS_DATE_FORMAT mặc định của session.

## 16. Duyệt cây JSON đệ quy và giới hạn độ sâu

Khi cấu trúc không cố định, có thể dùng procedure đệ quy nhận JSON_ELEMENT_T. Cần kiểm tra kiểu trước khi TREAT và đặt giới hạn depth.

~~~sql
CREATE OR REPLACE PROCEDURE inspect_json_tree (
    p_element IN JSON_ELEMENT_T,
    p_depth   IN PLS_INTEGER DEFAULT 0
) IS
    l_object JSON_OBJECT_T;
    l_array  JSON_ARRAY_T;
    l_keys   JSON_KEY_LIST;
    l_child  JSON_ELEMENT_T;
    l_type   VARCHAR2(20);
BEGIN
    IF p_element IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('PL/SQL NULL');
        RETURN;
    END IF;

    IF p_depth > 50 THEN
        RAISE_APPLICATION_ERROR(-20020, 'JSON nesting is too deep');
    END IF;

    IF p_element.is_object() THEN
        l_object := TREAT(p_element AS JSON_OBJECT_T);
        l_keys := l_object.get_keys();

        FOR i IN 1 .. l_keys.COUNT LOOP
            l_child := l_object.get(l_keys(i));
            inspect_json_tree(l_child, p_depth + 1);
        END LOOP;

    ELSIF p_element.is_array() THEN
        l_array := TREAT(p_element AS JSON_ARRAY_T);

        IF l_array.get_size() > 0 THEN
            FOR i IN 0 .. l_array.get_size() - 1 LOOP
                l_child := l_array.get(i);
                inspect_json_tree(l_child, p_depth + 1);
            END LOOP;
        END IF;

    ELSE
        IF p_element.is_string() THEN
            l_type := 'STRING';
        ELSIF p_element.is_number() THEN
            l_type := 'NUMBER';
        ELSIF p_element.is_boolean() THEN
            l_type := 'BOOLEAN';
        ELSIF p_element.is_null() THEN
            l_type := 'NULL';
        ELSE
            l_type := 'SCALAR';
        END IF;

        DBMS_OUTPUT.PUT_LINE(
            l_type || ': ' || p_element.to_string()
        );
    END IF;
END inspect_json_tree;
/
~~~

Một JSON document sâu có thể làm recursion tiêu thụ stack và CPU. Nếu chỉ cần xử lý path cố định, truy cập trực tiếp thường đơn giản hơn. Với payload không tin cậy, giới hạn cả độ sâu lẫn tổng số node được duyệt.

## 17. Phiên bản Oracle và khả năng tương thích

PL/SQL JSON object types như JSON_ELEMENT_T, JSON_OBJECT_T, JSON_ARRAY_T và JSON_SCALAR_T được giới thiệu trong Oracle Database 12c Release 2 (12.2). Các phiên bản sau mở rộng API và khả năng tương tác với SQL JSON.

Khi triển khai:
- Kiểm tra phiên bản Oracle và compatibility.
- Kiểm tra package/type JSON có sẵn và quyền sử dụng.
- Kiểm tra overload PARSE/TO_CLOB/TO_BLOB trên datatype đang dùng.
- Native SQL JSON data type chỉ có ở phiên bản hỗ trợ.
- JSON_TRANSFORM và các tính năng path mới phụ thuộc phiên bản.
- Không dùng method mới nếu production database chưa hỗ trợ.

Xem phiên bản:

~~~sql
SELECT banner
FROM v$version;
~~~

Nếu không có quyền đọc V$VERSION, hỏi DBA hoặc dùng view phiên bản được cấp quyền.

## 18. Hiệu năng và quản lý bộ nhớ

JSON DOM tạo cây trong bộ nhớ. Với document lớn, chi phí không chỉ là dung lượng CLOB nguồn mà còn gồm object/array nodes, scalar values, các bản sao và dữ liệu serialize.

Các nguyên tắc:
1. Parse một lần rồi dùng lại cây nếu cần đọc nhiều thuộc tính.
2. Không parse lại cùng document cho từng key.
3. Tránh CLONE toàn bộ document nếu chỉ cần sửa một node.
4. Dùng TO_CLOB thay TO_STRING cho tài liệu lớn.
5. Giải phóng temporary LOB do TO_CLOB/GET_CLOB tạo ra khi không còn cần.
6. Dùng SQL/JSON set-based khi truy vấn nhiều hàng.
7. Giới hạn kích thước, độ sâu và số phần tử đầu vào.
8. Không in payload lớn vào DBMS_OUTPUT trong production.
9. Không giữ DOM tree trong package global lâu hơn cần thiết.
10. Đo PGA, CPU và TEMP với dữ liệu đại diện.

### 18.1. Khi nào DOM phù hợp?

DOM phù hợp nếu:
- Cần sửa nhiều node trong một document.
- Có logic rẽ nhánh dựa trên cấu trúc JSON.
- Cần duyệt cây đệ quy.
- Cần tạo payload phức tạp từ nhiều nguồn.
- Document đủ nhỏ để giữ cây trong bộ nhớ.

### 18.2. Khi nào nên dùng SQL/JSON?

SQL/JSON phù hợp nếu:
- Cần lọc hàng theo thuộc tính JSON.
- Cần chiếu một vài scalar từ nhiều document.
- Cần biến array thành hàng quan hệ.
- Có thể thực hiện thao tác set-based trong một câu SQL.
- Không cần giữ và chỉnh sửa toàn bộ cây trong PL/SQL.

## 19. Ví dụ tổng hợp: cập nhật đơn hàng JSON

Tạo bảng sandbox:

~~~sql
CREATE TABLE json_order_demo (
    order_id NUMBER PRIMARY KEY,
    payload  CLOB,
    CONSTRAINT json_order_demo_ck CHECK (payload IS JSON)
);
~~~

Chèn document:

~~~sql
INSERT INTO json_order_demo(order_id, payload)
VALUES (
    1,
    '{
       "orderId":1,
       "status":"NEW",
       "customer":{"id":25,"name":"An"},
       "items":[
          {"sku":"KB-01","quantity":2,"price":150000},
          {"sku":"MS-02","quantity":1,"price":250000}
       ]
     }'
);

COMMIT;
~~~

Parse, validate, sửa và lưu:

~~~sql
DECLARE
    l_payload  CLOB;
    l_doc      JSON_OBJECT_T;
    l_customer JSON_OBJECT_T;
    l_items    JSON_ARRAY_T;
    l_item     JSON_OBJECT_T;
    l_output   CLOB;
BEGIN
    SELECT payload
    INTO l_payload
    FROM json_order_demo
    WHERE order_id = 1
    FOR UPDATE;

    l_doc := JSON_OBJECT_T.parse(l_payload);
    l_doc.on_error(1);

    IF NOT l_doc.has('status') THEN
        RAISE_APPLICATION_ERROR(-20030, 'Missing status');
    END IF;

    l_doc.put('status', 'PROCESSING');

    l_customer := l_doc.get_object('customer');
    l_customer.put('name', 'An Nguyen');

    l_items := l_doc.get_array('items');

    IF l_items.get_size() > 0 THEN
        -- GET_OBJECT trả reference tới object con trong array.
        l_item := l_items.get_object(0);
        l_item.put('quantity', 3);
    END IF;

    l_item := JSON_OBJECT_T();
    l_item.put('sku', 'HD-03');
    l_item.put('quantity', 1);
    l_item.put('price', 500000);
    l_items.append(l_item);

    l_output := l_doc.to_clob();

    UPDATE json_order_demo
    SET payload = l_output
    WHERE order_id = 1;

    COMMIT;

    IF l_output IS NOT NULL
       AND DBMS_LOB.ISTEMPORARY(l_output) = 1
    THEN
        DBMS_LOB.FREETEMPORARY(l_output);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF l_output IS NOT NULL
           AND DBMS_LOB.ISTEMPORARY(l_output) = 1
        THEN
            DBMS_LOB.FREETEMPORARY(l_output);
        END IF;

        ROLLBACK;
        RAISE;
END;
/
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT order_id,
       JSON_VALUE(payload, '$.status') AS status,
       JSON_VALUE(payload, '$.customer.name') AS customer_name,
       JSON_VALUE(payload, '$.items[0].quantity') AS first_quantity
FROM json_order_demo
WHERE order_id = 1;
~~~

Kết quả mong đợi: status là PROCESSING, customer_name là An Nguyen và first_quantity là 3.

Dọn sandbox:

~~~sql
DROP TABLE json_order_demo PURGE;
~~~

DROP là DDL và có implicit commit; chỉ thực hiện cleanup khi chắc chắn đây là bảng sandbox của bài thực hành.

## 20. Lỗi thường gặp khi thao tác JSON DOM

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Parse lỗi | JSON text sai cú pháp | Validate đầu vào và bắt lỗi parse |
| Sai root type | Dùng JSON_OBJECT_T cho root array | Chọn PARSE subtype đúng |
| GET_OBJECT trả NULL | Key thiếu hoặc node không phải object | HAS, IS_OBJECT và ON_ERROR |
| ORA-30625 | Gọi method trên JSON object instance NULL | Kiểm tra locator/object trước khi gọi |
| Getter trả NULL bất ngờ | Hành vi ON_ERROR mặc định hoặc missing key | Đặt ON_ERROR và kiểm tra HAS |
| Getter chuyển kiểu không mong muốn | GET_STRING/GET_NUMBER có thể convert | Kiểm tra IS_* hoặc GET_TYPE trước |
| JSON array đọc sai phần tử | Dùng index bắt đầu từ 1 | Dùng index từ 0 |
| PUT array làm tăng số phần tử | PUT mặc định chèn và dịch chuyển | Dùng OVERWRITE TRUE để thay |
| REMOVE làm sai index | Các phần tử phía sau dịch chuyển | Tính lại index sau khi xóa |
| Sửa node con nhưng không thấy trong bản clone | Đang sửa reference khác hoặc clone | Xác định reference/value semantics |
| Muốn sửa bản copy nhưng ảnh hưởng cây gốc | GET_OBJECT trả reference | Gọi CLONE trước khi sửa |
| JSON null bị coi là missing | Không dùng HAS/IS_NULL riêng | Phân biệt key thiếu và JSON null |
| Thay đổi cây nhưng bảng không đổi | Chưa serialize và DML | TO_CLOB/TO_STRING rồi INSERT/UPDATE |
| TO_STRING vượt giới hạn | Document lớn hơn VARCHAR2 buffer | Dùng TO_CLOB |
| Temporary CLOB bị giữ | Không cleanup kết quả serialize | ISTEMPORARY rồi FREETEMPORARY |
| Duyệt cây quá sâu | Không giới hạn recursion | Giới hạn depth và node count |
| Parse từng key lặp lại | Parse cùng document nhiều lần | Parse một lần rồi tái sử dụng DOM |

## 21. Quy trình xử lý JSON trong PL/SQL

Một luồng xử lý document có thể gồm:

1. Nhận JSON text từ CLOB/BLOB hoặc nguồn tích hợp.
2. Kiểm tra SQL NULL và giới hạn kích thước.
3. Parse bằng JSON_OBJECT_T hoặc JSON_ARRAY_T theo root type.
4. Đặt ON_ERROR phù hợp với chính sách validation.
5. Kiểm tra key bắt buộc bằng HAS.
6. Phân biệt key thiếu, JSON null và PL/SQL NULL.
7. Kiểm tra datatype bằng IS_OBJECT, IS_ARRAY, IS_STRING, IS_NUMBER hoặc IS_BOOLEAN.
8. Lấy scalar bằng GET_STRING/GET_NUMBER/GET_BOOLEAN.
9. Lấy node phức hợp bằng GET/GET_OBJECT/GET_ARRAY và hiểu reference semantics.
10. Dùng CLONE khi cần nhánh dữ liệu độc lập.
11. Thay đổi cây bằng PUT, PUT_NULL, APPEND, REMOVE hoặc RENAME_KEY.
12. Với array, phân biệt PUT insert với PUT overwrite.
13. Kiểm tra business rules và giới hạn document.
14. Serialize bằng TO_CLOB nếu document lớn.
15. INSERT/UPDATE trong transaction phù hợp.
16. Giải phóng temporary LOB được tạo trong quá trình serialize.
17. Ghi log lỗi parse/validation/DML mà không che exception gốc.

## 22. Những nhầm lẫn thường gặp

**JSON_OBJECT_T là cột JSON trong bảng.** Không đúng. Đây là object PL/SQL trong bộ nhớ; cần serialize hoặc chuyển sang kiểu SQL JSON phù hợp phiên bản rồi mới lưu.

**GET luôn trả VARCHAR2.** Không đúng. GET trả JSON_ELEMENT_T; getter typed trả scalar PL/SQL.

**JSON array bắt đầu từ index 1.** Không đúng. JSON_ARRAY_T dùng index từ 0.

**JSON object giữ thứ tự key như văn bản gốc.** Không nên dựa vào thứ tự key; dùng array nếu thứ tự là dữ liệu nghiệp vụ.

**Key không tồn tại giống key có JSON null.** Không đúng. HAS phân biệt key thiếu; IS_NULL xác định JSON null.

**PUT array mặc định ghi đè phần tử.** Không đúng. PUT mặc định chèn tại index và dịch chuyển phần tử sau; truyền OVERWRITE TRUE để thay.

**GET_OBJECT luôn tạo bản sao độc lập.** Không đúng. Node object/array phức hợp được trả theo reference semantics; dùng CLONE để có bản sao sâu.

**Sửa object con cần PUT lại vào object cha.** Không cần khi đang sửa node tham chiếu lấy từ cây gốc. PUT lại có thể dư thừa.

**GET_NUMBER và GET_STRING không bao giờ chuyển đổi kiểu.** Không đúng. Getter có thể chuyển đổi nếu có thể; kiểm tra IS_* khi cần datatype chính xác.

**JSON null là PL/SQL NULL.** Không đúng. JSON null là node trong cây JSON; PL/SQL NULL là trạng thái của biến/locator.

**Parse thành công đồng nghĩa dữ liệu đúng nghiệp vụ.** Không đúng. Vẫn cần validation key, type, range, quyền và quan hệ dữ liệu.

**TO_STRING phù hợp với mọi document.** Không đúng. VARCHAR2 có giới hạn; dùng TO_CLOB cho document lớn.

**TO_CLOB chỉ trả text, không cần cleanup.** Không đúng. Dạng function có thể tạo temporary CLOB; kiểm tra ISTEMPORARY và free khi dùng xong.

**PL/SQL DOM luôn tốt hơn SQL/JSON.** Không đúng. DOM phù hợp chỉnh sửa cây procedural; SQL/JSON phù hợp truy vấn và xử lý set-based.

**Sửa DOM tự động cập nhật bảng.** Không đúng. Cần serialize rồi thực hiện DML.

## 23. Bài tập tự luyện

1. Parse một JSON object có id, name và active bằng JSON_OBJECT_T.
2. Parse một root array bằng JSON_ARRAY_T.
3. Giải thích vai trò của JSON_ELEMENT_T và JSON_SCALAR_T.
4. Tạo object rỗng và thêm ba scalar bằng PUT.
5. Thêm JSON null bằng PUT_NULL.
6. Dùng HAS để kiểm tra key tồn tại.
7. Phân biệt key thiếu với key có JSON null.
8. Lấy string bằng GET_STRING và number bằng GET_NUMBER.
9. Lấy boolean bằng GET_BOOLEAN.
10. Dùng GET_OBJECT để đọc object customer lồng nhau.
11. Dùng GET_ARRAY để lấy danh sách items.
12. Dùng GET_KEYS để duyệt tất cả key.
13. Giải thích vì sao không dựa vào thứ tự key của object.
14. Tạo JSON_ARRAY_T và APPEND string, number, boolean.
15. Thêm JSON null vào array bằng APPEND_NULL.
16. Duyệt array với index bắt đầu từ 0.
17. Dùng PUT mặc định chèn một phần tử vào giữa array.
18. Dùng PUT với OVERWRITE TRUE để thay phần tử.
19. Xóa phần tử bằng REMOVE và quan sát index dịch chuyển.
20. Tạo object con rồi PUT vào root object.
21. So sánh reference semantics và value semantics.
22. Dùng CLONE để tạo bản sao object độc lập.
23. Viết procedure đệ quy duyệt cây JSON có giới hạn depth.
24. Bật ON_ERROR(1) và thử đọc một key không tồn tại.
25. Bật ON_ERROR(3) và thử đọc number từ JSON string.
26. Phân biệt TO_STRING, TO_CLOB và TO_BLOB.
27. Serialize object rồi lưu vào cột CLOB có IS JSON constraint.
28. Dùng JSON_TABLE để chuyển items array thành rows.
29. So sánh khi nào dùng JSON_OBJECT_T và khi nào dùng JSON_VALUE/JSON_TABLE.
30. Xây dựng procedure cập nhật status, customer và items của một order JSON rồi lưu lại trong transaction.

**JSON_OBJECT_T và JSON_ARRAY_T cho phép PL/SQL thao tác JSON như một cây trong bộ nhớ: parse document, kiểm tra kiểu, đọc scalar, sửa object/array lồng nhau và serialize kết quả.** Hãy nhớ array dùng index từ 0, phân biệt key thiếu với JSON null, hiểu reference semantics của GET và dùng CLONE khi cần bản sao độc lập. Bật ON_ERROR phù hợp, dùng PUT với OVERWRITE TRUE khi muốn thay phần tử array, rồi serialize và thực hiện DML nếu cần lưu thay đổi.


