# Building a Small Example to Observe a Message's Path

An easy way to understand Spring Messaging is to trace a message from the moment it is created, through a channel, until a handler receives and processes it. This lesson builds a small Java program using Spring Integration to observe that flow. The program creates a Message with a payload and headers, sends it into a DirectChannel, and prints the data on the receiving side.

The example runs inside a single process, without needing a broker, database, or server. This lets us focus on the basic components and clearly understand what the send operation does.

## 1. Objectives and Processing Flow

After finishing, you will recognize the roles of:

- **Producer:** the component that creates and sends messages.
- **Message:** the data envelope containing a payload and headers.
- **MessageChannel:** the point for sending messages to one or more handlers according to the channel's implementation.
- **MessageHandler:** the component that receives and processes messages.
- **DirectChannel:** a Spring Integration channel that delivers a message directly to a subscriber on the same calling thread.

Program flow:

~~~text
MessageFlowDemo (Producer)
        |
        | MessageBuilder.withPayload(...)
        | setHeader(...)
        v
   Message<String>
        |
        | DirectChannel.send(message)
        v
    DirectChannel
        |
        | invoke MessageHandler
        v
   MessageHandler (Consumer)
        |
        | read payload and headers
        v
   Print to console
        |
        v
   send() returns true
~~~

This example uses DirectChannel, so the handler is invoked synchronously on the sending thread. When reading the output, you will see the consumer's logs appear before the producer's send confirmation log.

## 2. Environment Preparation

Requirements:

- JDK 17 or higher.
- Apache Maven 3.8 or higher.
- Any Java IDE or terminal.
- Internet access the first time Maven downloads dependencies.

The example uses Spring Integration 6.4.6. The spring-integration-core module provides DirectChannel and depends on Spring Messaging, so the project can use Message, MessageBuilder, and MessageHandler without declaring a separate spring-messaging dependency.

Check the environment:

~~~shell
java -version
mvn -version
~~~

Both commands should display valid Java/Maven versions. If multiple JDKs are installed, check JAVA_HOME and verify Maven is using JDK 17 or higher.

## 3. Creating the Project Structure

Create a directory named message-flow-demo with the structure:

~~~text
message-flow-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MessageFlowDemo.java
~~~

pom.xml declares the Spring Integration Core dependency and plugins to compile and run the program with Maven.

## 4. Declaring Dependencies in pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-flow-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.4.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Points to note:

- spring-integration-core provides the DirectChannel implementation.
- Spring Messaging provides the Message, MessageChannel, MessageHandler, and MessageBuilder abstractions.
- maven.compiler.release sets the target Java API level to 17.
- exec-maven-plugin allows running a class with a main method directly from Maven.

If the project already uses Spring Boot, prefer letting Spring Boot dependency management manage compatible Spring Integration versions instead of pinning individual module versions yourself.

## 5. Writing MessageFlowDemo.java

Create the file src/main/java/demo/MessageFlowDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class MessageFlowDemo {

    public static void main(String[] args) {
        // 1. Create a channel for the producer to send messages.
        DirectChannel ordersChannel = new DirectChannel();

        // 2. Create a consumer and subscribe it to the channel.
        MessageHandler orderHandler = message -> {
            System.out.println("[consumer] payload = " + message.getPayload());
            System.out.println("[consumer] eventType = "
                    + message.getHeaders().get("eventType"));
            System.out.println("[consumer] correlationId = "
                    + message.getHeaders().get("correlationId"));
        };

        ordersChannel.subscribe(orderHandler);

        // 3. Create a message containing payload and headers.
        Message<String> message = MessageBuilder
                .withPayload("Order #1024 created")
                .setHeader("eventType", "order.created")
                .setHeader("correlationId", "corr-001")
                .build();

        // 4. Send the message through the channel.
        System.out.println("[producer] sending message");
        boolean sent = ordersChannel.send(message);

        // 5. Observe the send result.
        System.out.println("[producer] send result = " + sent);
    }
}
~~~

The program does not need to create a Spring ApplicationContext because the example directly instantiates the DirectChannel implementation and registers the handler using subscribe().

## 6. Running the Program and Observing Output

Open a terminal in the message-flow-demo directory and run:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.MessageFlowDemo
~~~

On the first run, Maven downloads the required dependencies. When the program runs successfully, the output is:

~~~text
[producer] sending message
[consumer] payload = Order #1024 created
[consumer] eventType = order.created
[consumer] correlationId = corr-001
[producer] send result = true
~~~

The order of output shows the message's path:

1. Producer prints a message preparing to send.
2. Producer calls ordersChannel.send(message).
3. DirectChannel delivers the Message to the registered handler.
4. Consumer reads the payload and headers, then prints them to the console.
5. Handler finishes, and the send operation returns true.
6. Producer prints the send result.

Because DirectChannel processes directly, the consumer's lines appear right inside the send() call. The program does not create a queue for the consumer to process later.

## 7. Analyzing Each Component

### 7.1. Creating DirectChannel

~~~java
DirectChannel ordersChannel = new DirectChannel();
~~~

DirectChannel is an implementation of SubscribableChannel in Spring Integration. It maintains a list of subscribers and dispatches messages to a suitable handler.

With one subscriber as in this example, the message is delivered to that subscriber. If there are multiple subscribers, DirectChannel uses its dispatching strategy to choose one handler to process a given send; it does not broadcast copies to all subscribers.

This is a point-to-point model. If the goal is to broadcast the same message to all subscribers, look into PublishSubscribeChannel.

### 7.2. Creating and Subscribing MessageHandler

~~~java
MessageHandler orderHandler = message -> {
    System.out.println(message.getPayload());
};

ordersChannel.subscribe(orderHandler);
~~~

MessageHandler is the contract for handling a Message<?>. The consumer does not need to know where the producer created the message; it only needs to read data according to the contract.

subscribe() registers the handler with the channel. Once registered, the channel can deliver messages to this handler.

In the example, a lambda is used as a concise implementation of MessageHandler. In larger applications, you can extract the handler into a dedicated class to manage business logic, logging, and testing.

### 7.3. Creating a Message with MessageBuilder

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order #1024 created")
        .setHeader("eventType", "order.created")
        .setHeader("correlationId", "corr-001")
        .build();
~~~

A message has two parts:

- Payload is the string Order #1024 created.
- Headers contain eventType and correlationId.

MessageBuilder helps construct messages clearly and supports adding metadata. MessageHeaders is designed to be immutable after the message is created; if you need to change headers, create a new message using the builder.

In real applications, the payload is usually a DTO or structured event class rather than an arbitrary string. Headers can contain a correlation ID, trace context, origin, or routing metadata. Avoid putting large business data into headers.

### 7.4. Sending the Message

~~~java
boolean sent = ordersChannel.send(message);
~~~

send() passes the message into the channel. With DirectChannel, dispatching to the handler happens on the calling thread. A return value of true indicates that the channel dispatched the message successfully according to the channel's send contract.

Do not interpret true as meaning all business work is complete or data has been durably persisted. The current example only prints content to the console; there is no database transaction, broker, or business acknowledgement mechanism.

## 8. Trying Changes to Understand the Path Better

After running the initial program, try the following changes to observe behavior.

### Changing the payload

Change:

~~~java
.withPayload("Order #1024 created")
~~~

to:

~~~java
.withPayload("Order #2048 created")
~~~

Rerun the program. The consumer will print the new payload while the headers remain unchanged. This demonstrates that payload and metadata are two separate parts of a Message.

### Adding a header

Add:

~~~java
.setHeader("source", "checkout-service")
~~~

In the handler, read the header:

~~~java
System.out.println("[consumer] source = "
        + message.getHeaders().get("source"));
~~~

The output will include an additional line:

~~~text
[consumer] source = checkout-service
~~~

The producer added metadata without having to change the signature of MessageHandler.

### Subscribing another handler

You can create an additional handler:

~~~java
MessageHandler auditHandler = message -> {
    System.out.println("[audit] received message id = "
            + message.getHeaders().getId());
};

ordersChannel.subscribe(auditHandler);
~~~

With DirectChannel, two subscribed handlers participate in point-to-point dispatching. Each send chooses only one handler to process it, depending on the load-balancing strategy. Therefore, do not expect both orderHandler and auditHandler to be invoked for the same message.

If you want both to receive every message, replace the channel with PublishSubscribeChannel:

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;

PublishSubscribeChannel ordersChannel = new PublishSubscribeChannel();
~~~

Handlers subscribed to PublishSubscribeChannel will all receive the published message. This is how to observe the difference between point-to-point and publish/subscribe.

### Observing behavior when there are no subscribers

Temporarily remove the line:

~~~java
ordersChannel.subscribe(orderHandler);
~~~

Then run again. DirectChannel has no handler to deliver the message to, so the send operation cannot be dispatched successfully; the send result will no longer be true. Depending on channel configuration and error handling, the application may also throw an exception when sending.

This shows that a producer needs a configured channel and an appropriate consumer before sending.

## 9. DirectChannel and Other Options

Different channels represent different communication policies:

| Channel | Dispatching behavior | Key characteristics |
|---|---|---|
| DirectChannel | One subscriber selected | Invokes handler directly on the sending thread |
| PublishSubscribeChannel | All subscribers | Broadcasts the same message to multiple handlers |
| ExecutorChannel | One subscriber selected | Offloads processing through an Executor, potentially asynchronous |
| QueueChannel | Stored in a queue | Consumers actively pull messages |

These implementations belong to Spring Integration. Spring Messaging provides the MessageChannel abstraction and related contracts; Spring Integration adds concrete channels and many integration components.

Choosing a channel should be based on requirements:

- Need immediate handling on the same thread: DirectChannel.
- Need to broadcast events to multiple components: PublishSubscribeChannel.
- Need to decouple processing timing with an executor: ExecutorChannel.
- Need to temporarily buffer messages for consumers to pull later: QueueChannel.

In-memory channels do not provide data durability when the application shuts down. If durable communication between processes or servers is needed, integrate an appropriate broker such as RabbitMQ, ActiveMQ, or a corresponding messaging system.

## 10. Common Mistakes When Building the Example

**Missing Spring Integration Core dependency:** if you only add a module that does not include DirectChannel, the compiler will report that package org.springframework.integration.channel cannot be found. Check the spring-integration-core dependency.

**Importing the wrong Message:** use org.springframework.messaging.Message, and do not confuse it with another class of a similar name.

**Forgetting to subscribe a handler:** creating a channel and calling send without a subscriber leaves no consumer to handle the message.

**Reading the wrong header:** the header name must match the key passed to setHeader() exactly. If the key does not exist, get() returns null.

**Confusing DirectChannel with a queue:** DirectChannel delivers directly to a handler. It does not store messages for later processing.

**Confusing send result with business result:** a successful send() only reflects delivery per the channel contract. If the handler writes to a database or calls an API, design transactions and error handling separately.

**Assuming multiple subscribers always receive the same message:** DirectChannel dispatches point-to-point. Use PublishSubscribeChannel when broadcasting is needed.

## 11. Extending the Example in Real Applications

Once you understand the basic path, you can extend it per your needs:

- Replace the String payload with an event class such as OrderCreated.
- Separate producer and consumer into distinct classes.
- Add a correlation ID to link logs across processing steps.
- Use PublishSubscribeChannel when multiple components care about the same event.
- Use ExecutorChannel when you want handlers to run via an executor.
- Use QueueChannel when you need a producer-push and consumer-pull model.
- Connect adapters to a broker when inter-process communication is required.
- Add validation, exception handling, retries, and latency monitoring when moving to a real environment.

Keep the minimal example simple while learning. When adding a broker, transactions, or multiple consumers, change one piece at a time and observe its effect on the message's path.

## 12. Key Takeaways

- A Message consists of a payload and headers; MessageBuilder helps create structured messages.
- The producer creates a message and sends it through a MessageChannel.
- The MessageHandler receives the message and performs processing.
- Spring Integration's DirectChannel delivers a message to one subscriber in a point-to-point model and processes synchronously on the sending thread.
- PublishSubscribeChannel broadcasts a message to all registered subscribers.
- The send() return value reflects delivery per the channel's contract, and does not mean business work is complete or data has been durably persisted.
- The example in this lesson runs in the same process and uses no broker; for durable network communication, integrate appropriate messaging infrastructure.
