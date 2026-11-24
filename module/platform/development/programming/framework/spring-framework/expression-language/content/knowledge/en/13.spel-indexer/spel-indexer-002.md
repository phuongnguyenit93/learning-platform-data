# Map Indexer by Key

SpEL uses square-bracket indexer syntax to access Map elements by key. Instead of reading data by position as with a List or array, the expression provides a key to retrieve the corresponding value in the map.

This syntax is useful when data is organized as key-value pairs, such as configuration, extended attributes, user information, metadata, or results returned from an API. The key can be a string, a number, or an object whose type matches the Map's key type. Understanding key types and how missing keys are handled helps expressions avoid reading or writing the wrong data.

## 1. Syntax for Accessing a Map by Key

Basic syntax:

~~~text
#settings['region']
#settings['language']
#settings['timeout']
~~~

In the example, settings is a variable holding a Map in the EvaluationContext. The content between the square brackets is an expression that determines the key. Single quotes create a string literal, so 'region' is a String key.

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Map<String, Object> settings = new HashMap<>();
settings.put("region", "ap-southeast-1");
settings.put("language", "vi");
settings.put("timeout", 30);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("settings", settings);

Expression expression =
        parser.parseExpression("#settings['region']");

String region = expression.getValue(context, String.class);

System.out.println(region); // ap-southeast-1
~~~

SpEL evaluates the expression #settings to obtain the Map, then uses the key 'region' to retrieve the value. The return value of the indexer is the value stored under that key.

Use square brackets when the goal is to access a specific key of a Map. This notation clearly expresses a key-value lookup and avoids confusion with property access on a Java object.

## 2. Dynamic Variable as Key

A key does not have to be a fixed literal. You can place the key in an EvaluationContext variable and use that variable inside the indexer.

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("region", "ap-southeast-1");
settings.put("language", "vi");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("settings", settings);
context.setVariable("selectedKey", "language");

Expression expression =
        parser.parseExpression("#settings[#selectedKey]");

Object value = expression.getValue(context);

System.out.println(value); // vi
~~~

Here #selectedKey is evaluated first to obtain the string language, and then the Map is looked up using that key. This approach is useful when the key depends on a request, user selection, or a value computed from another part of the expression.

You can use a variable to select a key without creating a new expression string for each key. This helps reuse the Expression and keeps input data separate from SpEL syntax.

## 3. Keys Can Be the Result of an Expression

The content inside square brackets is evaluated as a SpEL expression. Therefore, a key can be formed from a variable, a property, or the result of an operation.

~~~text
#settings[#prefix + 'Region']
#settings[#request.locale]
#settings[#selectedKeys[0]]
~~~

Example:

~~~java
Map<String, String> labels = new HashMap<>();
labels.put("message.vi", "Xin chào");
labels.put("message.en", "Hello");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("labels", labels);
context.setVariable("locale", "vi");

Expression expression = parser.parseExpression(
        "#labels['message.' + #locale]"
);

String message = expression.getValue(context, String.class);
~~~

The expression constructs the key message.vi by concatenating the string message. with the value of the locale variable. The Map returns the value corresponding to the newly constructed key.

When a key is computed, check its final value and its data type. A misspelled key or a different type can still result in the element not being found even when the Map contains similar-looking data.

## 4. Distinguishing String Keys from Numeric Keys

A key's type is part of the key's identity in a Map. A Map can contain the String key "1001" and the Integer key 1001 as two distinct entries.

Example:

~~~java
Map<Object, String> values = new HashMap<>();
values.put("1001", "string key");
values.put(1001, "integer key");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("values", values);

Object stringValue = parser.parseExpression(
        "#values['1001']"
).getValue(context);

Object integerValue = parser.parseExpression(
        "#values[1001]"
).getValue(context);
~~~

The two expressions look up two keys with different types. You should not assume that SpEL will automatically convert every key to String or Integer as you intend.

For a Map with Integer keys, you can use a numeric literal:

~~~text
#codes[1001]
~~~

For a Map with enum keys or another object type, pass a variable with the exact key type:

~~~java
context.setVariable("statusKey", OrderStatus.ACTIVE);

Expression expression =
        parser.parseExpression("#statusLabels[#statusKey]");
~~~

Finding an element depends on the equals() and hashCode() rules of the key type as well as the actual key stored in the Map. For custom object keys, ensure the equals/hashCode implementation is stable and consistent.

## 5. Accessing Nested Maps

A Map can hold another Map as a value. You can chain multiple indexers to access deep into a key-value structure.

Configuration example:

~~~java
Map<String, Object> mail = new HashMap<>();
mail.put("host", "smtp.example.com");
mail.put("port", 587);

Map<String, Object> config = new HashMap<>();
config.put("mail", mail);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("config", config);

Expression expression = parser.parseExpression(
        "#config['mail']['host']"
);

String host = expression.getValue(context, String.class);
~~~

SpEL performs two lookups: first retrieving the value of the key mail from config, and then retrieving the key host from the nested Map. Each level must return an object that can be indexed in the next step.

You can access deeper levels:

~~~text
#config['mail']['smtp']['host']
#config['features']['checkout']['enabled']
~~~

If an intermediate key does not exist or the value there is null, the subsequent indexing expression can produce an error. For deeply nested structures, check each level or normalize the data before evaluation.

## 6. Distinguishing a Missing Key from a Null Value

When a Map does not contain a key, a normal lookup returns null. However, null can also be a valid value stored in the Map. Therefore, simply checking whether the indexer result is null is not enough to distinguish the two situations.

Example:

~~~java
Map<String, Object> values = new HashMap<>();
values.put("presentNull", null);

System.out.println(values.containsKey("presentNull")); // true
System.out.println(values.containsKey("missing"));     // false
~~~

If you need to distinguish them, use containsKey():

~~~text
#settings.containsKey('region')
~~~

You can check the key before reading:

~~~text
#settings.containsKey('region') and #settings['region'] != null
~~~

Because AND short-circuits, if the key does not exist, the right-hand side is not evaluated. This avoids reading the value further when the first condition is already false.

With nested Maps, check each level before indexing the next level. For example:

~~~text
#config.containsKey('mail') and #config['mail'] != null
~~~

Only after confirming mail exists and is not null should you evaluate the expression reading host. If you need to check multiple levels in one rule, group conditions with parentheses to make the order explicit.

## 7. Using an Indexer to Update Values in a Map

Indexers are not only for reading. When the EvaluationContext and the Map allow writing, you can assign a value to a key:

~~~java
Map<String, Object> settings = new HashMap<>();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("settings", settings);

Expression assignment = parser.parseExpression(
        "#settings['theme'] = 'dark'"
);

assignment.getValue(context);

System.out.println(settings.get("theme")); // dark
~~~

If the key does not exist yet, the assignment can add a new entry to a mutable Map. If the key already exists, the corresponding value is replaced.

You can use Expression.setValue to separate the key path from the new value:

~~~java
Expression theme = parser.parseExpression(
        "#settings['theme']"
);

theme.setValue(context, "light");
~~~

Both ways modify the Map. Writability depends on whether the Map supports modification and whether the context has property/indexer access that permits writing. Immutable or read-only Maps can reject the operation and throw an exception.

Remember that assigning to a Map mutates object state. If the Map is shared or used as global configuration, the change can affect other parts of the application.

## 8. Using Map Keys in Conditions and Compound Expressions

Values retrieved from a Map can be used directly in comparisons, arithmetic operations, or logical conditions.

~~~text
#settings['retryCount'] > 3
#settings['region'] == 'ap-southeast-1'
#settings['enabled'] == true
#settings['price'] * #settings['quantity']
~~~

Example:

~~~java
Map<String, Object> orderData = new HashMap<>();
orderData.put("price", new BigDecimal("19.90"));
orderData.put("quantity", new BigDecimal("3"));

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orderData", orderData);

Expression expression = parser.parseExpression(
        "#orderData['price'] * #orderData['quantity']"
);

BigDecimal total = expression.getValue(context, BigDecimal.class);
~~~

In this case, the Map stores data by key and the expression computes the total from two values. The numeric type of the values affects the operation and result type. If the Map contains Object values, ensure the values have types suitable for the calculation the expression performs.

With heterogeneous data, check types beforehand or convert the data in the Java layer. You should not assume every value in a Map is numeric just because a few current entries have type BigDecimal.

## 9. Map Keys and Property Access Are Different Access Mechanisms

A Map stores data by key, whereas a Java object usually exposes data via properties or getters. For a Map, indexer syntax clearly expresses the key to look up:

~~~text
#settings['region']
~~~

For an object with a region property, the usual way to write it is:

~~~text
#profile.region
~~~

Do not replace an indexer with property access just because a Map key looks like a property name. Square brackets help show that the string region is a key in a Map.

This distinction is especially important when data structures come from JSON or an API. A JSON object may be deserialized into a Map; in that case, the JSON fields become key-value entries. If the data is deserialized into a Java DTO, they are instead accessed through the corresponding properties.

## 10. Combining Maps with Lists and Objects

A Map can contain Lists, arrays, or other objects. SpEL allows combining a Map indexer with positional indexers or property access.

Example data structure:

~~~java
Map<String, Object> response = new HashMap<>();
response.put("items", List.of(
        Map.of("sku", "A-01"),
        Map.of("sku", "B-02")
));

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("response", response);
~~~

You can read the first SKU:

~~~text
#response['items'][0]['sku']
~~~

The path consists of three steps: get the key items in the outer Map, get the element at position 0 of the List, and then get the key sku in the inner Map.

With structures combining multiple collections, break the path down step by step when debugging. If one step returns null or a type that does not support the next indexer, the error usually appears at a later step rather than necessarily at the first key.

## 11. Maps and Implementation Types

SpEL's indexer syntax works with the Map interface, so common implementations can be used, such as:

- HashMap: looks up keys via hashCode/equals, does not guarantee iteration order.
- LinkedHashMap: preserves entry insertion order.
- TreeMap: sorts keys according to a comparator or natural order.
- EnumMap: uses an enum as the key, suitable for a fixed set of enum keys.
- Immutable Map: suitable for read-only data, does not accept writes.

Key-based lookup still relies on the Map contract. Differences between implementations affect ordering, performance, null-key capability, and updatability.

If an expression is read-only, consider providing an unmodifiable Map or a read-only copy. If an expression needs to write, verify that the Map actually supports that operation and that the object is not shared outside the intended scope.

## 12. Data Control and Safety When Using Maps in SpEL

Maps often contain flexible data that may come from requests, JSON, configuration, or databases. Therefore, keys and values can be missing, have the wrong type, or be controlled by an external source.

Some practical guidelines:

1. Clearly define the key type and value type of the Map.
2. Use single-quoted string literals for String keys.
3. Use variables of the appropriate type when keys are numbers, enums, or custom objects.
4. Check containsKey and null before deep access.
5. Normalize input data before evaluating expressions.
6. Only allow writing to a Map when the use case requires it.
7. Do not put Maps containing secrets or unnecessary internal data into the context.
8. Use a restricted EvaluationContext if expressions can be edited by untrusted parties.

In particular, do not treat using a Map instead of an entity as an automatic security measure. If the Map contains sensitive information, an expression can still read those keys when the context permits it.

## 13. Diagnosing Errors When Indexing Maps

| Symptom | Common Cause | How to Check |
|---|---|---|
| Result returns null | Key does not exist or value is actually null | Use containsKey to distinguish |
| Key not found despite looking like the same characters | Actual key type differs from the type in the expression | Check the class of the key |
| Nested Map access fails | An intermediate level does not exist or is null | Check each key in order |
| Key assignment fails | Immutable Map or accessor does not allow writing | Check implementation and write permissions |
| Dynamic key is incorrect | Variable or key-producing expression returns an unexpected value | Print or inspect the key value before lookup |
| Value cannot be used in an operation | Value has an incompatible type | Check runtime type and convert |
| Expression reads a property by mistake | Used dot notation instead of indexer for a Map | Use explicit map['key'] syntax |

When debugging, you can inspect the Map directly in Java before evaluating SpEL: print keySet, check containsKey, and get the class of keys/values. Then evaluate a simple indexer expression before chaining multiple levels or adding operations.

## 14. Key Takeaways

The Map indexer uses square brackets and a key to retrieve a value, such as #settings['region']. A key can be a literal, a variable, or the result of an expression. Key type is critical: String "1001" and Integer 1001 are two different keys.

You can chain multiple indexers to access nested Maps or combine Maps with Lists and objects. If a key does not exist, the lookup result is usually null; use containsKey when you need to distinguish a missing key from a null value. An indexer can also write values if the Map and EvaluationContext permit it.

Define key/value types clearly, check data levels before deep access, and grant write access only when truly needed. Using indexers clearly helps SpEL expressions work with flexible key-value data while remaining easy to understand and control.